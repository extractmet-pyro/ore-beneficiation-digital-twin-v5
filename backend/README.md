# Ore Beneficiation Digital Twin — backend (gravity + WHIMS)

First-principles process simulator, **model-predictive control** layer and **machine-learning**
layer for a gravity and magnetic iron-ore beneficiation plant — the classical Indian flowsheet
that makes three products from one run-of-mine stream:

```
ROM ore -> jaw crusher -> sizing screen (closed with the secondary cone)
        -> ROTARY SCRUBBER (clay removal) -> discharge trommel
             +10 mm  -> LUMP JIG ------------------> LUMP ORE          (blast-furnace feed)
                                 floats -> tertiary cone -> back to the jig / to the fines
             -10 mm  -> SCREW CLASSIFIER
                          sand  -> 2 mm screen -> FINES JIG ---------> SINTER FINES
                                               -> cyclone -> SPIRALS -> SINTER FINES
                                                                 middling -> SHAKING TABLES -> SINTER FINES
                          slime -> DESLIMING CYCLONES -> WHIMS ------> PELLET-PLANT FEED
    tailings -> thickener -> TSF ;  overflow -> water recovery -> recycle
```

## Why the state matrix matters here

Every stream is a **36 size-class x 15 liberation-class mass matrix**. Particle **density**
follows directly from the liberation class — free quartz at 2.65 SG, free hematite at 5.15 — so
jigs, spirals and tables separate on exactly the axis the matrix already tracks, each with its own
size-dependent sharpness. Magnetic susceptibility follows the same axis, so the WHIMS works off
the same state. Nothing is re-derived from a bulk assay anywhere in the circuit.

That is what makes the model behave like a plant: a jig is sharp on 40 mm lumps and useless below
1 mm, a spiral takes over from 3 mm to 75 um, a table is the sharpest of the three but only on a
narrow deslimed feed — and the twin reproduces each of those limits from the same physics rather
than from three separate fitted correlations.

| Layer | Contents |
|---|---|
| `app/twin` | Size / liberation / density state, crushing and screening, rotary scrubber, jigs, screw classifier, hydrocyclones, spirals, shaking tables, WHIMS, thickening, flowsheet solver with Wegstein-accelerated recycles, 33 hierarchical constraints, 8 objectives, 8 soft sensors |
| `app/control` | FOPDT identification from the twin, RGA pairing, instrument-readiness gate, condensed DMC with soft zone constraints, closed-loop simulator, DCS hand-over payload |
| `app/ml` | Twin-sampled dataset builder, gradient-boosted soft sensors, hybrid twin-residual models, isolation-forest anomaly detection, PSI drift monitoring, model registry |
| `app/services` | Plant register, 168 h replay historian with seven scripted faults, simulation, washability, optimisation, live state, overview, unit detail, MPC, ML, diagnostics, data quality, metadata |
| `app/adapters` | OPC UA / PI Web API / MQTT / Kafka / CSV / SQL / REST historian adapters |

## The control story

Alumina, not silica, is the binding specification for this ore, and it is carried into the lump
product as a **clay coating on otherwise good ore**. Scrubber duty strips that coating; the jig cut
density rejects what the scrubber missed at the cost of lump yield. Those two handles interact
strongly (relative gains far from 1), which is precisely the case for a multivariable controller
rather than two single loops — and the advisory page says so.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# docs: http://localhost:8000/docs
pytest -q
```

## Deploy

* **Render**: `render.yaml` blueprint (set `ALLOWED_ORIGINS` to the operator-desk URL).
* **Docker / on-prem edge**: `docker build -t ore-ben-twin . && docker run -p 8000:8000 ore-ben-twin`.
* Set `API_KEY` to require `X-API-Key` on `/api/v1`; set `HISTORIAN_TYPE` to connect a real historian.

## API map (`/api/v1`)

`plants` · `simulation` (run, sensitivity, tornado, compare, grade-recovery, washability) ·
`optimization` (run, monte-carlo, pareto) · `mpc` (config, identification, step-response, solve,
simulate, advisory, handover) · `ml` (status, models, predict, hybrid, importance, learning-curve,
partial-dependence, anomaly, drift, scan, retrain) · `live` · `overview` · `units` ·
`diagnostics` · `data-quality` · `timeseries` · `metadata`

All demo sites are anonymised as **Industry-X** (IX-OB-01 / 02 / 03).
