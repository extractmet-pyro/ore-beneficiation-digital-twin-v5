"""Production historian adapters.

Optional client libraries are imported lazily so the demo deployment on Render
does not need them: install ``asyncua`` (OPC UA), ``paho-mqtt`` (MQTT),
``confluent-kafka`` (Kafka) or ``sqlalchemy`` + a DB driver (SQL) only on sites
that use them. Missing configuration raises :class:`IntegrationNotConfigured`.
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pandas as pd

from app.adapters.base import HistorianAdapter
from app.core.config import Settings
from app.core.exceptions import IntegrationNotConfigured


def _grid(start: datetime, end: datetime, step: timedelta) -> list[datetime]:
    n = int((end - start) / step) + 1
    return [start + i * step for i in range(n)]


def _resample(df: pd.DataFrame, stamps: list[datetime]) -> tuple[list, list]:
    """Align irregular (ts, value) samples to a regular grid with last-value hold."""
    if df.empty:
        return [None] * len(stamps), ["bad"] * len(stamps)
    s = df.set_index("ts")["value"].sort_index()
    idx = pd.DatetimeIndex(stamps)
    r = s.reindex(s.index.union(idx)).ffill().reindex(idx)
    vals = [None if pd.isna(v) else float(v) for v in r.tolist()]
    return vals, ["good" if v is not None else "bad" for v in vals]


class OPCUAAdapter(HistorianAdapter):
    """OPC UA client (current values) — node id = OPCUA_NAMESPACE + tag."""
    name = "opcua"

    def __init__(self, s: Settings) -> None:
        if not s.OPCUA_ENDPOINT:
            raise IntegrationNotConfigured("OPCUA_ENDPOINT is not set")
        self.s = s

    async def _read(self, tags: list[str]) -> dict[str, dict[str, Any]]:
        try:
            from asyncua import Client  # type: ignore
        except ImportError as exc:
            raise IntegrationNotConfigured("Install 'asyncua' to enable the OPC UA adapter") from exc
        out: dict[str, dict[str, Any]] = {}
        async with Client(url=self.s.OPCUA_ENDPOINT) as client:
            if self.s.OPCUA_USERNAME:
                client.set_user(self.s.OPCUA_USERNAME)
                client.set_password(self.s.OPCUA_PASSWORD)
            for t in tags:
                node = client.get_node(f"{self.s.OPCUA_NAMESPACE}{t}")
                dv = await node.read_data_value()
                ts = dv.SourceTimestamp or datetime.now(timezone.utc)
                out[t] = {"value": float(dv.Value.Value) if dv.Value.Value is not None else None,
                          "quality": "good" if dv.StatusCode.is_good() else "bad",
                          "timestamp": ts.isoformat(), "age_s": (datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc)).total_seconds()}
        return out

    def read_current(self, plant_id: str, tags: list[str] | None = None, ts: datetime | None = None):  # noqa: ANN201
        return asyncio.run(self._read(tags or []))

    def read_history(self, plant_id: str, tags: list[str], start: datetime, end: datetime, step: timedelta):  # noqa: ANN201
        raise IntegrationNotConfigured("OPC UA HA (history) is served by the site historian; configure PI/SQL for history")

    def health(self) -> dict[str, Any]:
        return {"adapter": self.name, "endpoint": self.s.OPCUA_ENDPOINT}


class PIWebAPIAdapter(HistorianAdapter):
    """AVEVA/OSIsoft PI Web API adapter (points resolved by path \\\\server\\tag)."""
    name = "pi"

    def __init__(self, s: Settings) -> None:
        if not (s.PI_WEB_API_URL and s.PI_DATA_SERVER):
            raise IntegrationNotConfigured("PI_WEB_API_URL and PI_DATA_SERVER must be set")
        self.s = s
        auth = (s.PI_USERNAME, s.PI_PASSWORD) if s.PI_USERNAME else None
        self.client = httpx.Client(base_url=s.PI_WEB_API_URL.rstrip("/"), auth=auth, timeout=15.0, verify=True)
        self._webids: dict[str, str] = {}

    def _webid(self, tag: str) -> str:
        if tag not in self._webids:
            r = self.client.get("/points", params={"path": f"\\\\{self.s.PI_DATA_SERVER}\\{tag}"})
            r.raise_for_status()
            self._webids[tag] = r.json()["WebId"]
        return self._webids[tag]

    def read_current(self, plant_id: str, tags: list[str] | None = None, ts: datetime | None = None):  # noqa: ANN201
        out = {}
        for t in tags or []:
            r = self.client.get(f"/streams/{self._webid(t)}/value")
            r.raise_for_status()
            j = r.json()
            tstamp = datetime.fromisoformat(j["Timestamp"].replace("Z", "+00:00"))
            val = j.get("Value")
            out[t] = {"value": float(val) if isinstance(val, (int, float)) else None,
                      "quality": "good" if j.get("Good", True) else "bad", "timestamp": j["Timestamp"],
                      "age_s": (datetime.now(timezone.utc) - tstamp).total_seconds()}
        return out

    def read_history(self, plant_id: str, tags: list[str], start: datetime, end: datetime, step: timedelta):  # noqa: ANN201
        stamps = _grid(start, end, step)
        out: dict[str, Any] = {"timestamps": stamps, "values": {}, "quality": {}}
        for t in tags:
            r = self.client.get(f"/streams/{self._webid(t)}/interpolated",
                                params={"startTime": start.isoformat(), "endTime": end.isoformat(),
                                        "interval": f"{int(step.total_seconds())}s"})
            r.raise_for_status()
            items = r.json().get("Items", [])
            df = pd.DataFrame([{"ts": pd.Timestamp(i["Timestamp"]), "value": i["Value"] if isinstance(i["Value"], (int, float)) else None}
                               for i in items])
            out["values"][t], out["quality"][t] = _resample(df, stamps)
        return out

    def health(self) -> dict[str, Any]:
        try:
            ok = self.client.get("/system").status_code == 200
        except httpx.HTTPError:
            ok = False
        return {"adapter": self.name, "url": self.s.PI_WEB_API_URL, "connected": ok}


class StreamingAdapter(HistorianAdapter):
    """MQTT or Kafka subscriber keeping a rolling in-memory buffer of JSON tag messages.

    Message format: ``{"tag": "PI-310", "value": 101.2, "ts": "2026-09-22T08:00:00Z", "quality": "good"}``.
    """

    def __init__(self, s: Settings, kind: str) -> None:
        self.s = s
        self.name = kind
        self.buffer: dict[str, list[tuple[datetime, float | None, str]]] = {}
        self._lock = threading.Lock()
        if kind == "mqtt" and not s.MQTT_BROKER_URL:
            raise IntegrationNotConfigured("MQTT_BROKER_URL is not set")
        if kind == "kafka" and not s.KAFKA_BOOTSTRAP_SERVERS:
            raise IntegrationNotConfigured("KAFKA_BOOTSTRAP_SERVERS is not set")
        threading.Thread(target=self._run, daemon=True).start()

    def _ingest(self, payload: bytes) -> None:
        m = json.loads(payload)
        ts = datetime.fromisoformat(str(m.get("ts")).replace("Z", "+00:00"))
        with self._lock:
            buf = self.buffer.setdefault(m["tag"], [])
            buf.append((ts, m.get("value"), m.get("quality", "good")))
            del buf[:-20000]

    def _run(self) -> None:
        if self.name == "mqtt":
            import paho.mqtt.client as mqtt  # type: ignore
            host, _, port = self.s.MQTT_BROKER_URL.replace("mqtt://", "").partition(":")
            c = mqtt.Client()
            c.on_message = lambda _c, _u, msg: self._ingest(msg.payload)
            c.connect(host, int(port or 1883))
            c.subscribe(self.s.MQTT_TOPIC_PREFIX + "#")
            c.loop_forever()
        else:
            from confluent_kafka import Consumer  # type: ignore
            c = Consumer({"bootstrap.servers": self.s.KAFKA_BOOTSTRAP_SERVERS, "group.id": "mining-twin",
                          "auto.offset.reset": "latest"})
            c.subscribe([self.s.KAFKA_TOPIC])
            while True:
                msg = c.poll(1.0)
                if msg is not None and not msg.error():
                    self._ingest(msg.value())

    def read_current(self, plant_id: str, tags: list[str] | None = None, ts: datetime | None = None):  # noqa: ANN201
        now = datetime.now(timezone.utc)
        out = {}
        with self._lock:
            for t in tags or list(self.buffer):
                if self.buffer.get(t):
                    tt, v, q = self.buffer[t][-1]
                    out[t] = {"value": v, "quality": q, "timestamp": tt.isoformat(), "age_s": (now - tt).total_seconds()}
        return out

    def read_history(self, plant_id: str, tags: list[str], start: datetime, end: datetime, step: timedelta):  # noqa: ANN201
        stamps = _grid(start, end, step)
        out: dict[str, Any] = {"timestamps": stamps, "values": {}, "quality": {}}
        with self._lock:
            for t in tags:
                df = pd.DataFrame([{"ts": a, "value": b} for a, b, _ in self.buffer.get(t, [])])
                out["values"][t], out["quality"][t] = _resample(df, stamps)
        return out

    def health(self) -> dict[str, Any]:
        return {"adapter": self.name, "tags_buffered": len(self.buffer)}


class TabularAdapter(HistorianAdapter):
    """CSV file, SQL table or REST endpoint in long format: columns ``ts, tag, value[, quality]``."""

    def __init__(self, s: Settings, kind: str) -> None:
        self.s = s
        self.name = kind
        if kind == "csv" and not s.CSV_HISTORIAN_PATH:
            raise IntegrationNotConfigured("CSV_HISTORIAN_PATH is not set")
        if kind == "sql" and not s.SQL_DATABASE_URL:
            raise IntegrationNotConfigured("SQL_DATABASE_URL is not set")
        if kind == "rest" and not s.REST_HISTORIAN_URL:
            raise IntegrationNotConfigured("REST_HISTORIAN_URL is not set")

    def _frame(self, tags: list[str], start: datetime, end: datetime) -> pd.DataFrame:
        if self.name == "csv":
            df = pd.read_csv(self.s.CSV_HISTORIAN_PATH, parse_dates=["ts"])
        elif self.name == "sql":
            try:
                from sqlalchemy import create_engine, text  # type: ignore
            except ImportError as exc:
                raise IntegrationNotConfigured("Install 'sqlalchemy' and a DB driver for the SQL adapter") from exc
            eng = create_engine(self.s.SQL_DATABASE_URL)
            q = text(f"SELECT ts, tag, value FROM {self.s.SQL_TABLE} WHERE ts BETWEEN :a AND :b")
            with eng.connect() as con:
                df = pd.read_sql(q, con, params={"a": start, "b": end}, parse_dates=["ts"])
        else:
            headers = {"Authorization": f"Bearer {self.s.REST_HISTORIAN_TOKEN}"} if self.s.REST_HISTORIAN_TOKEN else {}
            r = httpx.get(self.s.REST_HISTORIAN_URL, params={"tags": ",".join(tags), "start": start.isoformat(),
                                                              "end": end.isoformat()}, headers=headers, timeout=20)
            r.raise_for_status()
            df = pd.DataFrame(r.json())
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
        if df["ts"].dt.tz is None:
            df["ts"] = df["ts"].dt.tz_localize("UTC")
        return df[df["tag"].isin(tags) & (df["ts"] >= start) & (df["ts"] <= end)]

    def read_current(self, plant_id: str, tags: list[str] | None = None, ts: datetime | None = None):  # noqa: ANN201
        now = ts or datetime.now(timezone.utc)
        df = self._frame(tags or [], now - timedelta(hours=6), now)
        out = {}
        for t, g in df.sort_values("ts").groupby("tag"):
            last = g.iloc[-1]
            out[t] = {"value": float(last["value"]), "quality": str(last.get("quality", "good")),
                      "timestamp": last["ts"].isoformat(), "age_s": (now - last["ts"].to_pydatetime()).total_seconds()}
        return out

    def read_history(self, plant_id: str, tags: list[str], start: datetime, end: datetime, step: timedelta):  # noqa: ANN201
        stamps = _grid(start, end, step)
        df = self._frame(tags, start, end)
        out: dict[str, Any] = {"timestamps": stamps, "values": {}, "quality": {}}
        for t in tags:
            out["values"][t], out["quality"][t] = _resample(df[df["tag"] == t][["ts", "value"]], stamps)
        return out

    def health(self) -> dict[str, Any]:
        return {"adapter": self.name}


def build_adapter(s: Settings) -> HistorianAdapter | None:
    """Return a production adapter for HISTORIAN_TYPE, or None for the mock replay."""
    kind = s.HISTORIAN_TYPE.lower()
    if kind == "mock":
        return None
    if kind == "opcua":
        return OPCUAAdapter(s)
    if kind == "pi":
        return PIWebAPIAdapter(s)
    if kind in ("mqtt", "kafka"):
        return StreamingAdapter(s, kind)
    if kind in ("csv", "sql", "rest"):
        return TabularAdapter(s, kind)
    raise IntegrationNotConfigured(f"Unknown HISTORIAN_TYPE '{s.HISTORIAN_TYPE}'")
