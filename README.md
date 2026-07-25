# PathFinder — Career Decision Intelligence

> Career decision intelligence that reads your resume, forecasts which of your skills are rising or fading, maps future-proof career pathways, **matches you to real open jobs**, recommends grounded courses, and **tracks your progress** as you close the gaps — for both students and working professionals.

**Live app:** https://pathfinder-383713992026.asia-south1.run.app/#/ · Health: https://pathfinder-383713992026.asia-south1.run.app/api/health
_Powered by Google Cloud (Cloud Run · Gemini · Cloud SQL), project `promptwar-501405`, region `asia-south1`._
Specs & design: [../SPEC.md](../SPEC.md) · [../ARCHITECTURE.md](../ARCHITECTURE.md) · [ARCHITECTURE_GRAPH.md](ARCHITECTURE_GRAPH.md) · [plan.md](plan.md)

---

## Capabilities

Every feature runs against real data and real algorithms:

- **Accounts, auth & saved history** — email/password with PBKDF2-hashed credentials (never plaintext), stateless JWT sessions, per-user saved analyses you can re-open and delete, and full account deletion. Durable on **Cloud SQL Postgres**.
- **Resume → skills** — real PDF/text extraction + **Gemini** (`gemini-2.5-flash`) skill extraction (live), grounded to a 40-skill O*NET/ESCO taxonomy; deterministic local extractor as fallback.
- **Skill-demand forecasting** — a real, reproducible log-linear trend model over a 36-month India demand series (e.g. *Data Entry ≈ −18%/yr ▼*, *Power BI ≈ +21%/yr ▲*).
- **3 ranked career pathways** — composite score = skill coverage × demand growth × salary uplift × achievability, each with an explainable *why this fits you*.
- **Real job matching (Professional)** — live openings from **Adzuna** (India) matched to your skills with a fit %, the exact gap skills to qualify, grounded gap-courses, and a direct apply link. Pluggable JSearch/ATS sources; deep-link only, no scraping.
- **Learning tracker (closed loop)** — track recommended courses; completing them raises your pathway coverage (e.g. *Reporting Analyst 33% → 74%*).
- **Grounded courses in two tracks** — Free · Govt/YouTube/public (SWAYAM, NPTEL, YouTube, freeCodeCamp, Kaggle, MS Learn) and Paid · certificate (Coursera, edX) — from a real 57-entry catalog, zero hallucinated links.
- **Two tailored experiences** — Student (courses, higher studies, trending skills) and Working Professional (real jobs), from one profile via a persona toggle.
- **Platform import** — bring your profile from LinkedIn / Indeed / Naukri (paste or upload your export); ToS-compliant.
- **Transparent multi-agent pipeline** with a per-agent trace in the UI.

AI capabilities sit behind **pluggable providers**: the app runs fully on deterministic local providers and upgrades to Gemini / Vertex RAG / BQML by setting env vars — no code change. Job data uses **Adzuna** (live) with a curated fallback.

_Selected as a **Top-101 finalist**, Google Cloud Gen AI Academy — APAC Cohort 2 (Education & Lifelong Learning)._

---

## Quickstart (local)

Requires Python 3.9+.

```bash
cd pathfinder/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m seed                      # create tables + materialise the demand series
uvicorn app.main:app --reload       # serves API + web app on http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000**, click **See a live example**, or upload a resume PDF.
Optional: `python make_sample_resume.py` generates a sample resume PDF at `app/data/sample_resume_asha.pdf`.

Run the end-to-end pipeline test (no server needed):

```bash
cd pathfinder/backend && python ../tests/smoke_pipeline.py
```

---

## Project structure

```
pathfinder/
├── Dockerfile              # single container: API + static SPA
├── deploy.sh               # one-command Cloud Run deploy
├── backend/
│   ├── requirements.txt
│   ├── seed.py             # tables + demand_series.json
│   ├── make_sample_resume.py
│   └── app/
│       ├── main.py         # FastAPI app (API under /api, SPA at /)
│       ├── config.py       # env-driven settings
│       ├── database.py · models.py · schemas.py · security.py · deps.py
│       ├── routers/        # auth · analysis · history · catalog · meta · jobs · learning
│       ├── agents/orchestrator.py   # SkillsExtractor→MarketAnalyst→PathwayPlanner→ROIForecaster
│       ├── engines/        # datasets · forecast · taxonomy · rag · providers · jobs · jd_parser · matching
│       └── data/           # skills · role_skill_matrix · salaries · courses · jobs_sample (curated)
├── frontend/               # static SPA (no build step): index.html + css/ + js/
└── adk/adk_app.py          # ADK SequentialAgent harness (SPEC R6)
```

---

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | — | Create account → JWT |
| POST | `/api/auth/login` | — | Log in → JWT |
| GET | `/api/auth/me` | ✅ | Current user |
| DELETE | `/api/auth/me` | ✅ | Delete account (cascades history) |
| POST | `/api/analysis/` | optional | Analyze (`file` PDF, `resume_text`, or `manual_profile`). Saved if logged in |
| GET | `/api/history/` | ✅ | List saved analyses |
| GET | `/api/history/{id}` | ✅ | Re-open a saved analysis |
| DELETE | `/api/history/{id}` | ✅ | Delete one analysis |
| POST | `/api/jobs/match` | optional | Real jobs matched to skills (Adzuna live) — fit %, gap skills, gap-courses, apply link |
| GET · POST | `/api/learning/` | ✅ | List / add tracked courses |
| PATCH · DELETE | `/api/learning/{id}` | ✅ | Update status (saved / in_progress / completed) / remove |
| GET | `/api/learning/progress` | ✅ | Pathway coverage before→after as you complete courses |
| PATCH | `/api/auth/me` | ✅ | Set persona (student / professional) |
| GET | `/api/catalog/skills` · `/courses` | — | Taxonomy + catalog |
| GET | `/api/meta/` · `/api/health` | — | Version, active providers, dataset counts |

---

## Pluggable Google Cloud providers

Each capability has a local default and a GCP implementation activated by env vars (no code change). See [`app/engines/providers.py`](backend/app/engines/providers.py).

| GCP service | Activate with | Falls back to |
|---|---|---|
| **Gemini** (skill extraction) | `GEMINI_API_KEY` | local taxonomy extractor |
| **Vertex AI RAG** (course grounding) | `VERTEX_PROJECT` + `VERTEX_RAG_CORPUS` | local catalog retrieval |
| **BigQuery + BQML** (`ML.FORECAST`) | `BQML_DATASET` | local log-linear forecaster |
| **ADK** (multi-agent) | `python adk/adk_app.py` | native orchestrator (identical output) |
| **Adzuna** (real job data) | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` (live) · `RAPIDAPI_KEY` for JSearch | curated job set |
| **Cloud SQL / AlloyDB** (persistence) | `DATABASE_URL` + `--add-cloudsql-instances` | SQLite (dev) |
| **Cloud Run** (hosting) | `./deploy.sh` | local `uvicorn` |

`GET /api/health` reports which provider is live for each capability.

---

## Deploy to Google Cloud Run

```bash
cd pathfinder
./deploy.sh promptwar-501405            # REGION=asia-south1 by default
```

The script enables the required APIs, builds from the `Dockerfile` via Cloud Build, and deploys a public Cloud Run service. It prints the live URL and generates a strong `JWT_SECRET` (override by exporting `JWT_SECRET`).

### Durable persistence — Cloud SQL Postgres (live)

The production service persists accounts, saved history, and the learning tracker on **Cloud SQL Postgres** (`pg8000`), so data survives redeploys. `deploy.sh` wires it through when you export the connection:

```bash
gcloud sql instances create pathfinder-db --database-version=POSTGRES_15 --tier=db-f1-micro --region=asia-south1
gcloud sql databases create pathfinder --instance=pathfinder-db
CONN=<PROJECT>:<REGION>:pathfinder-db
CLOUDSQL_CONN="$CONN" \
DATABASE_URL="postgresql+pg8000://<user>:<pass>@/pathfinder?unix_sock=/cloudsql/$CONN/.s.PGSQL.5432" \
GEMINI_API_KEY=... ADZUNA_APP_ID=... ADZUNA_APP_KEY=... ./deploy.sh promptwar-501405
```

Without `DATABASE_URL`, the app falls back to on-container SQLite (fine for local dev).

---

## Responsible AI & reproducibility

- **Grounded**: courses come only from `courses.json`; the model narrates, it never invents figures.
- **Deterministic**: identical input → identical analysis (forecasts, ranking) — verified by `tests/smoke_pipeline.py`.
- **Transparent**: every pathway shows skill coverage, demand growth, salary basis, and its data source; the demand series is generated from documented parameters (synthetic where public data has gaps, disclosed in the UI footer).
- **Data ownership**: raw resumes are not stored after parsing; users can delete any analysis or their whole account.

---

## Golden path

1. Open the live URL → **Sign up** (or continue as a guest).
2. Click **See a live example** (or upload a resume PDF / connect a platform).
3. See skill chips tagged ▲ rising / ▼ declining (Data Entry shows the ▼ anomaly).
4. Review 3 ranked pathways → open one for the forecast chart, the *"Why this fits you"* panel, and grounded courses (free + paid).
5. Switch to the **Professional** persona → **Find matching jobs** → real Adzuna openings with a fit %, gap skills, and exactly what to learn.
6. Hit **＋ Track** on a course → open **My learning** → mark it complete → watch your pathway match rise (e.g. 33% → 74%).
7. See the multi-agent trace; log out and back in → **My analyses** persists on Cloud SQL.
