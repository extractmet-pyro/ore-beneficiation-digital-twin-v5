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
| Build Command | `pip install --upgrade pip && pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 180` |
| Health Check Path | `/health` |
| Region | Singapore |

> **Root Directory is the one people miss.** Without it Render looks for `requirements.txt` at
> the repository root, does not find it, and the build fails.
>
> **`--port $PORT` is mandatory.** Render assigns the port at runtime; a hard-coded 8000 fails
> the health check and the deploy hangs.

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
| `HYBRID_SAMPLES` | `320` — use `140` on the free plan |
| `OPTIMIZER_MAX_EVALS` | `240` — use `120` on the free plan |
| `ALLOWED_ORIGINS` | *leave blank, set in step D* |

Wait for **Live**, then:

```bash
curl https://<your-api>.onrender.com/health
```

Expect `"status":"ok"` and `"version":"OBDT-2026.10.5"`. **Copy that URL.**

The service answers `/health` within about 25 ms of start. It then spends two to three minutes
warming models on a background thread — watch the log for `validation runs warmed`. Until that
line appears the heavy pages still work, just slowly.

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

Measured on one full core. A free Render instance is roughly ten to twenty times slower, which
is why the warm-up matters so much there.

| First request to… | Lazy (before) | Warmed (now) |
|---|---|---|
| `/hybrid/config` | 25 300 ms | **41 ms** |
| `/hybrid/compare` | 30 200 ms | **3 ms** |
| `/validation/run` (full suite) | 37 400 ms | **61 ms** |
| `/mpc/identification` | 3 600 ms | **7 ms** |
| `/simulation/run` | 158 ms | **23 ms** |

Peak memory is **260 MB**, inside the free plan's 512 MB. The binding constraint on free is CPU,
not memory.

**Before a client demonstration**, on the free plan:

```bash
curl https://<api>.onrender.com/health          # wake it, then wait for the warm-up in the log
```

Free instances sleep after 15 minutes of inactivity, and a cold start re-runs the warm-up. For
anything you are being watched during, use Starter — it does not idle.

**If warm-up is too slow on free**, set `HYBRID_SAMPLES=140`. That halves the design of
experiments behind the hybrid models. The models are slightly less well fitted; the gating
behaviour and every acceptance criterion are unaffected.

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
