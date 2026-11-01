# DEPLOY — Ore Beneficiation Digital Twin v5

Backend as a **Web Service**, operator desk as a **Blueprint**. Twenty minutes end to end.

---

## A · Push

```bash
git init && git add . && git commit -m "Ore beneficiation digital twin v5"
git branch -M main
git remote add origin git@github.com:<org>/<repo>.git
git push -u origin main
```

Check no real secrets went in: `git ls-files | grep -i env` must list only the two
`.env.example` files.

---

## B · Backend — Web Service

Render → **New +** → **Web Service** → connect the repository.

| Field | Value |
|---|---|
| **Root Directory** | **`backend`** |
| Language | Python 3 |
| Branch | `main` |
| Build Command | `pip install --upgrade pip && pip install -r requirements.txt && python scripts/precompute.py` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 180` |
| Health Check Path | `/health` |
| Region | Singapore |

> **Root Directory is the one people miss.** Without it Render looks for `requirements.txt` at
> the repository root, does not find it, and the build fails.
>
> **`--port $PORT` is mandatory.** Render assigns the port at runtime; a hard-coded 8000 fails
> the health check and the deploy hangs.
>
> **`python scripts/precompute.py` is what makes the free plan usable.** It trains the hybrid
> models, the ML registry and the whole replay history during the **build**, on the build
> machine, and writes them into the image. The service then loads them in about a third of a
> second instead of spending minutes of a tenth of a core training them while your requests
> queue behind. Expect the build to take **five to seven minutes**; the deploy log prints each
> stage. Drop it and everything still works, just slowly — see *Performance* below.

Environment variables:

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.3` |
| `APP_ENV` | `production` |
| `LOG_LEVEL` | `INFO` |
| `MODEL_VERSION` | `OBDT-2026.10.5` |
| `DEMO_MODE` | `true` |
| `HISTORIAN_TYPE` | `mock` |
| `ALLOWED_ORIGIN_REGEX` | `https://.*\.onrender\.com` |
| `WARM_ON_START` | `true` |
| `WARM_HYBRID` | `true` |
| `HYBRID_SAMPLES` | `320` |
| `REPLAY_STEPS_PER_HOUR` | `2` — drop to `1` only if the build times out |
| `OPTIMIZER_MAX_EVALS` | `240` — use `120` on the free plan |
| `ALLOWED_ORIGINS` | *leave blank, set in step D* |

The last two are the only ones worth touching for the free plan, and neither is about start-up —
the build handles that. `OPTIMIZER_MAX_EVALS` governs the constrained search, which runs on
request and cannot be precomputed.

Wait for **Live**, then:

```bash
curl https://<your-api>.onrender.com/health
```

Expect `"status":"ok"` and `"version":"OBDT-2026.10.5"`. **Copy that URL.**

Watch the start-up log. You want to see this, and it should take under a second:

```
warm cache loaded in 0.31s (24.7 MB, built …): 4 hybrid models, 5 ML models, 1011 replay nodes, 3 MPC identifications, 3 validation runs
warm-up complete
```

If instead you see `no warm cache at … — layers will be built on demand`, the precompute step
did not run or did not match. The service still works; it will just be slow for the first few
minutes. Check the build log for the `precompute complete` line.

---

## C · Operator desk — Blueprint

The root `render.yaml` defines **only** the static site, so applying it cannot create a second
API beside the one from step B.

1. Render → **New +** → **Blueprint** → select the repository → **Apply**.
2. It prompts for `BACKEND_BASE_URL`. **Set it to the API URL from step B**: `https`, no
   trailing slash, service root only — not `/api/v1`, which the desk appends itself.
3. Leave `API_KEY` and `APP_PASSWORD` blank.

If `BACKEND_BASE_URL` is missing the **build fails on purpose**, with the fix printed in the
log. That is deliberate: the alternative is a desk that silently serves captured demonstration
payloads and looks fine.

---

## D · Close the loop

On the **API** service set:

```
ALLOWED_ORIGINS = https://<your-desk>.onrender.com
```

Exact origin — scheme included, no trailing slash, no path. Redeploy the API.

Then on the desk: **Admin → Backend**. It must report the live API, `OBDT-2026.10.5` and a
round-trip time.

---

## If the desk says "MOCK fallback, backend unreachable"

That message appears only on a **network-layer** failure. An HTTP error would surface as an
error instead. So it is one of four things. Open the desk, press **F12**, reload, and read the
Console and Network tabs.

| What you see | Cause | Fix |
|---|---|---|
| Calls going to `localhost:8000` | `BACKEND_BASE_URL` never set | Step C.2, then redeploy |
| `Blocked: mixed content` | Desk is https, backend URL is http | Use `https` |
| `No 'Access-Control-Allow-Origin' header` | Desk origin not in `ALLOWED_ORIGINS` | Step D |
| Pending, then fails after ~60 s | Free instance asleep; cold start | `curl .../health` to wake it |

Fastest check of all, in the Console:

```js
window.OBDT_CONFIG.BACKEND_BASE_URL
```

If that prints `http://localhost:8000`, step C.2 is your entire problem.

---

## Performance

### What was slow, and what fixed it

Two separate problems, both now fixed.

**1 · Models were trained on the running instance.** Three minutes of CPU at start-up. A full
core absorbs that; a free instance is about a tenth of a core, so it became roughly half an hour
of saturated CPU during which every request queued behind the training. Warming at start-up
made the free plan *worse*, not better. The work now happens in the build.

**2 · The hourly caches were being missed.** The replay history is cached per plant and per
hour. Several pages swept their window from the current fractional hour — `13.47, 14.47, …` —
which matched no cached node, so each chart re-solved the twin twenty-four times over. Those
sweeps are now snapped onto the cached grid, and the grid is built half-hourly to match the
finest step any page asks for.

First request to each endpoint, measured on one full core, no cache priming:

| Endpoint | Before | After |
|---|---|---|
| Start-up warm-up | 188 000 ms | **330 ms** |
| `/validation/run` (full acceptance suite) | 37 400 ms | **7 ms** |
| `/hybrid/compare` | 30 200 ms | **4 ms** |
| `/hybrid/config` | 25 300 ms | **4 ms** |
| `/diagnostics/residuals` | 9 765 ms | **30 ms** |
| `/data-quality/report` | 9 186 ms | **56 ms** |
| `/live/tag-trend` (6 tags, 24 h, 30 min step) | 7 350 ms | **74 ms** |
| `/live/trend` | 4 616 ms | **4 ms** |
| `/overview/shifts` | 4 541 ms | **4 ms** |
| `/ml/anomaly` | 3 204 ms | **294 ms** |
| `/mpc/identification` | 2 806 ms | **6 ms** |
| `/plant3d/model` | 8 ms | **8 ms** |
| `/simulation/run` | 158 ms | **173 ms** |

The last two rows are there on purpose. The 3-D scene and the circuit solve were never the
problem and are not faster now — a single solve has always been about 150 ms. Everything that
*was* slow was slow because it was training a model or re-solving a cached hour, and that is
what moved to the build.

Scale the rest by ten to twenty for a free instance: the slowest page becomes a few seconds
rather than the better part of a minute. Peak resident memory is **297 MB** against the free
plan's 512 MB, with the warm cache loaded. Memory is not the binding constraint; CPU is, and the
build now carries almost all of it.

### What the free plan still cannot do

Being straight with you, because no amount of tuning changes these:

- **It sleeps after 15 minutes of inactivity.** Waking it takes **50 to 60 seconds**, and that is
  Render starting the container, not our code. Nothing in this repository can shorten it.
- **It is a shared fractional CPU.** `/optimization/search` and `/mpc/closed-loop` genuinely
  compute on request and cannot be precomputed; expect a few seconds each.

Three ways to live with that, in order of what I would actually do:

| | What | Cost | Good for |
|---|---|---|---|
| **1** | **`MOCK_MODE=true` on the desk** | free | A client demonstration. The desk serves its captured payloads, every page opens instantly, nothing can be asleep. The 3-D model, the hybrid attribution, the acceptance report — all of it works. What you lose is running *new* scenarios. |
| **2** | **Free, woken beforehand** | free | Your own evaluation. `curl https://<api>/health` and wait for `warm cache loaded`, then it is responsive until it idles out. |
| **3** | **Starter, $7/month** | $7/mo | Anything you are being watched during. No sleeping, a full CPU share, and it is the only one of the three where a prospect clicking around unannounced sees the system at its best. |

For a client demonstration specifically: **use 1 or 3, never 2.** A 60-second blank page while a
free instance wakes is the worst possible first impression of a system whose whole argument is
that it responds fast enough to sit beside a control room.

### If the build times out

The precompute step takes five to seven minutes, most of it the replay grid. Set
`REPLAY_STEPS_PER_HOUR=1` on the API service and rebuild: the build drops to about two minutes
and the cache to about 13 MB. The cost is that the Live page's instrument board — the only chart
that samples sub-hourly — goes back to solving its own snapshots. Everything else is unaffected.

Raising it above `2` is not worth it. Each step doubles both the build time and the cache's
resident memory, and no page in the desk samples finer than half-hourly.

`HYBRID_SAMPLES=140` halves the hybrid part of the build. The models are slightly less well
fitted; the gating behaviour and every acceptance criterion are unaffected.

---

## Alternatives

**Both services from one blueprint.** Rename and push:

```bash
mv render.yaml render.frontend.yaml && mv render.full.yaml render.yaml
git commit -am "Deploy both from the blueprint" && git push
```

Then **New +** → **Blueprint** → Apply, and set the two cross-reference URLs afterwards.

**On premise**, which is what a real plant gets — no process, assay or ore-body data leaves the
site and no outbound internet connection is needed:

```bash
cd backend  && docker build -t obdt-api . && docker run -d -p 8000:8000 --env-file .env obdt-api
cd frontend && docker build -t obdt-web --build-arg BACKEND_BASE_URL=http://obdt-api:8000 . \
            && docker run -d -p 8080:80 obdt-web
```

Chapter 5 of the deployment guide covers sizing, systemd units, historian adapters and the DCS
interface.
