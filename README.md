# Ore Beneficiation Digital Twin — v5

**Gravity + WHIMS iron-ore beneficiation plant.** A first-principles process simulator, a plant
3-D model bound to live state, a hybrid mechanistic-and-data-driven layer, a supervisory model
predictive controller, and a formal validation and acceptance framework — with a browser
operator desk built in plain CSS, JavaScript and Three.js.

Built by **Extractmet Private Limited**, incubated at the IIT Madras Research Park, in
association with the Centre for Pyrometallurgy, IIT Madras. All reference plants are anonymised
as *Industry-X*.

```
backend/     FastAPI + Python — twin, hybrid, MPC, ML, validation.  Deploys as a Render web service.
frontend/    CSS + JavaScript + Three.js operator desk.             Deploys as a Render static site.
render.yaml  Blueprint that deploys both from this one repository.
```

---

## What is in v5

v5 adds three things to the v4 twin, in answer to three client questions.

### 1 · Plant 3-D model (`backend/app/plant3d/`, `frontend/js/viz/plantmodel.js`)

A tagged, levelled, clash-checked 3-D model of the plant whose **appearance is driven by the
twin**, not by a drawing. 33 tagged assets, 30 material routes, five elevations. Colour follows
the chosen overlay (constraint status, duty, motor power, throughput, stream grade, slurry
density); the halo follows the constraint status; clicking an asset opens its datasheet, live
duty and connected streams.

Nothing about the layout is in the front end. The backend sends a scene graph; the viewer builds
meshes from it. Replace the asset register — or import the site's own CAD or scan model — and the
picture changes with no front-end edit.

Site geometry is brought in through `app/plant3d/importers.py`: glTF/GLB natively, IFC, AVEVA
RVM, STEP and point clouds through conversion, with tag matching that **refuses to bind on a
guess** and a closed-form Umeyama registration from control points.

### 2 · Hybrid mechanistic + data driven (`backend/app/hybrid/`)

Not a slogan and not a blend. Six named compositions are implemented and compared; the one in
service is **gated residual**:

> the physics predicts, a learned model predicts the physics' residual, the correction is bounded
> in magnitude, and it is tapered to zero as the operating point leaves the data the learner was
> trained on.

The guarantee that matters: **outside the learned domain the hybrid prediction equals the
mechanistic prediction exactly**, and that is demonstrated by an extrapolation walk in the
acceptance suite rather than asserted. Every prediction carries an attribution — how much came
from the physics, how much from the learner — because a number an operator cannot decompose is a
number an operator will not act on.

### 3 · Measurable acceptance criteria (`backend/app/validation/`)

A complete verification-and-validation layer:

| Piece | What it is |
|---|---|
| `criteria.py` | 14 KPI criteria and 12 system criteria, graded Class A/B/C, each naming its measurement basis, averaging window and minimum sample count |
| `metrics.py` | bias, MAE, RMSE, MAPE, R², Nash–Sutcliffe, Theil's U2, Willmott's d, Bland–Altman, paired t, KS, Durbin–Watson, interval coverage, residual profile |
| `scenarios.py` | the validated operating envelope and 17 test scenarios across accuracy, behaviour, fault detection, fail-safe and declared exclusions |
| `protocol.py` | six gates from data readiness to handover, with roles, entry, activities, evidence, exit and a stated consequence of failure |
| `runner.py` | executes the suite and returns a verdict for every criterion |
| `report.py` | renders the whole run as a signable Acceptance Test Report |

Three rules are enforced in code, not just written down:

- **No tolerance is tighter than the measurement it is graded against.** Every limit is a stated
  multiple of the reference instrument's own repeatability. There is a unit test for it.
- **Assays gate on absolute error; tonnages gate on relative error.** That is how each is
  contracted. Applying both to both silently makes the tighter one the real criterion, and which
  one that is changes from plant to plant.
- **A measure that cannot discriminate is reported, not used.** A correlation statistic on a
  variable whose whole range over the test period sits inside its own measurement noise grades
  the noise. It is computed, shown, and explicitly excluded from the verdict with the reason
  recorded.

---

## Running it locally

```bash
# API + twin engine
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000              # docs at http://localhost:8000/docs

# operator desk, in a second terminal
cd frontend
npm install                                            # jsdom, for the tests only
node scripts/serve.mjs                                 # http://localhost:8080
```

The desk reads `config.js`. For local use the committed file already points at
`http://localhost:8000`; on Render it is written at build time from the environment.

### Tests

```bash
cd backend  && python -m pytest -q          # 182 tests
cd frontend && node --test tests/app.test.mjs   # 21 tests
```

### Running the acceptance suite

```bash
curl "localhost:8000/api/v1/validation/run?plant_id=IX-OB-01&section=all&tests_pass=true"
curl "localhost:8000/api/v1/validation/report.md?plant_id=IX-OB-01" -o Acceptance_Test_Report.md
```

or open **Validation & acceptance → Run & verdict** on the desk.

### Refreshing the offline payloads

The desk falls back to captured payloads when the API is unreachable, so a demonstration works
on a plane. After changing the backend:

```bash
cd frontend
node scripts/capture-mock.mjs http://localhost:8000          # resumes; add --force to redo all
```

A cold capture takes several minutes because the hybrid endpoints train models and the
validation endpoints run the full acceptance suite. It is resumable by design.

---

## Deploying to GitHub and Render

> **See `DEPLOY.md` for the step-by-step card**, including the "MOCK fallback, backend
> unreachable" diagnosis table and the performance notes for the free plan. The summary below
> is the same procedure in brief.

### 1 · Push

```bash
git init
git add .
git commit -m "Ore beneficiation digital twin v5"
git branch -M main
git remote add origin git@github.com:<org>/<repo>.git
git push -u origin main
```

### 2 · Deploy both services from the blueprint

In the Render dashboard: **New + → Blueprint → connect this repository → Apply**. Render reads
`render.yaml` at the root and creates two services. `rootDir` is what lets one repository hold
both: each build runs inside its own folder.

| Service | Type | Root | Free plan? |
|---|---|---|---|
| `obdt-v5-api` | Python web service | `backend` | Works, but a cold start takes ~60 s and the optimiser and validation suite are slow on fractional CPU |
| `obdt-v5-web` | Static site | `frontend` | Yes — global CDN, no cold start |

### 3 · Close the loop between them

Neither URL is known until the first deploy, so two variables are left blank in the blueprint:

| Service | Variable | Set it to |
|---|---|---|
| `obdt-v5-api` | `ALLOWED_ORIGINS` | the desk URL, e.g. `https://obdt-v5-web.onrender.com` |
| `obdt-v5-web` | `BACKEND_BASE_URL` | the API URL, e.g. `https://obdt-v5-api.onrender.com` |

Redeploy both. Open the desk and check **Admin → Backend**: it should report the live API, the
model version and a round-trip time.

### 4 · Optional hardening

- Set `API_KEY` on **both** services to the same value to require `X-API-Key` on `/api/v1`.
  Note that anything the desk sends is visible to a browser user, so this gates casual access,
  not a determined one. For a real deployment put the desk behind the plant's SSO.
- Set `AUTH_MODE=password` and `APP_PASSWORD` for a shared password gate on the desk.
- Leave `MOCK_MODE=auto` so the desk degrades to captured payloads instead of an error page when
  the API is cold or unreachable.

### Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request: both test suites, a syntax check
over every front-end module, and the **acceptance suite against all three reference plants**. A
change that breaks a validation criterion fails the build rather than turning up at a factory
acceptance test. On `main` it also generates and uploads the acceptance test reports as build
artefacts.

### On-premise instead of Render

Render is for demonstrations and evaluations. A production deployment runs on the plant's own
server or VM behind the site firewall, with no outbound internet connection required:

```bash
cd backend && docker build -t obdt-api . && docker run -p 8000:8000 --env-file .env obdt-api
cd frontend && docker build -t obdt-web . && docker run -p 8080:80 obdt-web
```

No process data, assay data or ore-body data leaves the site in either arrangement.

---

## API map

| Group | Prefix | What it covers |
|---|---|---|
| Plants | `/api/v1/plants` | register, tags, configuration schema |
| Simulation | `/api/v1/simulation` | run, sensitivity, tornado, compare, grade–recovery, washability |
| Optimisation | `/api/v1/optimization` | constrained search, Monte Carlo, Pareto |
| MPC | `/api/v1/mpc` | identification, step response, solve, closed-loop study, DCS hand-over |
| ML | `/api/v1/ml` | soft sensors, importance, partial dependence, anomaly, drift |
| **Hybrid** | `/api/v1/hybrid` | composition, attribution, domain check, head-to-head, extrapolation |
| **Plant 3-D** | `/api/v1/plant3d` | scene graph, live state, asset drill-down, levels, clash, glTF manifest, CAD import |
| **Validation** | `/api/v1/validation` | criteria, envelope, scenarios, protocol, run, report, certificate |
| Live / diagnostics | `/api/v1/live`, `/diagnostics`, `/data-quality`, `/timeseries` | snapshot, balances, reconciliation, residuals, instrument health |

Interactive documentation at `/docs`.

---

## Earlier versions

This package is self-contained and does not replace anything. The copper concentrator twin
(Streamlit and web), the BHQ iron-ore twin, and the v4 gravity + WHIMS twin remain exactly as
delivered.

---

© Extractmet Private Limited. Commercial in confidence. Reference work is published only in
anonymised form.
