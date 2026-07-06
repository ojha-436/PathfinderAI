# PathFinder — AI Career & Reskilling Decision Advisor (v2)

> Upload your resume → PathFinder forecasts which of your skills are rising or dying, returns **3 ranked, future-proof career pathways** (with payoff, an explainable *why*, and the first 3 real courses), and **saves every analysis to your account**.

Built for the **Google Cloud Gen AI Academy — APAC C2**, *Education & Lifelong Learning* track.
Specs & design: [../SPEC.md](../SPEC.md) · [../ARCHITECTURE.md](../ARCHITECTURE.md)

**Live app:** https://pathfinder-823065407403.asia-south1.run.app · Health: https://pathfinder-823065407403.asia-south1.run.app/api/health
_(Deployed on Google Cloud Run, project `promptwar-501405`, region `asia-south1`.)_

---

## What's real here (not a demo)

Every P0 feature works against real data and real algorithms — no canned responses:

- **Accounts + auth + saved history** (the headline of v2): email/password with PBKDF2-hashed credentials (never plaintext), stateless JWT sessions, per-user saved analyses you can re-open and delete, and full account deletion.
- **Resume → skills**: real PDF text extraction + **Gemini** (`gemini-2.5-flash`) skill extraction when `GEMINI_API_KEY` is set (live on the deployed service), grounded back to a 40-skill O*NET/ESCO taxonomy; deterministic local extractor as fallback.
- **Platform connectors**: import your profile/skills from **LinkedIn / Indeed / Naukri** (paste your profile or upload the export the platform gives you) → analyzed by the same pipeline. ToS-compliant: you bring your data, nothing is scraped on your behalf.
- **Demand forecasts**: a real **log-linear trend model** over a curated 36-month India demand series — reproducible run-to-run (e.g. *Data Entry ≈ −18%/yr ▼*, *Power BI ≈ +21%/yr ▲*).
- **Pathways**: composite ranking = skill coverage × demand growth × salary uplift × achievability.
- **Grounded courses in two categories**: (1) **Free · Govt/YouTube/public** (SWAYAM, NPTEL, YouTube, freeCodeCamp, Kaggle, Microsoft Learn) and (2) **Paid · certificate** (Coursera, edX). Retrieved only from a real 57-entry catalog — **zero hallucinated courses by construction**.
- **4-agent pipeline** with a per-agent trace surfaced in the UI.

All five GCP services are wired behind **pluggable providers** (see below): the app runs fully offline on local providers and upgrades to Gemini / Vertex RAG / BQML by setting env vars — no code change.

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

Open **http://127.0.0.1:8000**, click **Try Asha's sample**, or upload a resume PDF.
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
│       ├── routers/        # auth · analysis · history · catalog · meta
│       ├── agents/orchestrator.py   # SkillsExtractor→MarketAnalyst→PathwayPlanner→ROIForecaster
│       ├── engines/        # datasets · forecast · taxonomy · rag · providers
│       └── data/           # skills · role_skill_matrix · salaries · courses (curated)
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
| **Cloud Run** (hosting) | `./deploy.sh` | local `uvicorn` |

`GET /api/health` reports which provider is live for each capability.

---

## Deploy to Google Cloud Run

```bash
cd pathfinder
./deploy.sh promptwar-501405            # REGION=asia-south1 by default
```

The script enables the required APIs, builds from the `Dockerfile` via Cloud Build, and deploys a public Cloud Run service. It prints the live URL and generates a strong `JWT_SECRET` (override by exporting `JWT_SECRET`).

### Durable persistence (production)

The default deploy uses on-container **SQLite pinned to one instance** — accounts/history persist while the instance is warm but reset on redeploy. For durable persistence, provision Cloud SQL Postgres and deploy with:

```bash
gcloud sql instances create pathfinder-db --database-version=POSTGRES_15 --tier=db-f1-micro --region=asia-south1
gcloud sql databases create pathfinder --instance=pathfinder-db
# then redeploy with:
gcloud run deploy pathfinder --source . --region asia-south1 --allow-unauthenticated \
  --add-cloudsql-instances <CONN_NAME> \
  --set-env-vars "APP_ENV=production,JWT_SECRET=...,DATABASE_URL=postgresql+pg8000://user:pass@/pathfinder?unix_sock=/cloudsql/<CONN_NAME>/.s.PGSQL.5432"
```

(Add `pg8000` to `requirements.txt` for the pure-Python Postgres driver.)

---

## Responsible AI & reproducibility

- **Grounded**: courses come only from `courses.json`; the model narrates, it never invents figures.
- **Deterministic**: identical input → identical analysis (forecasts, ranking) — verified by `tests/smoke_pipeline.py`.
- **Transparent**: every pathway shows skill coverage, demand growth, salary basis, and its data source; the demand series is generated from documented parameters (synthetic where public data has gaps, disclosed in the UI footer).
- **Data ownership**: raw resumes are not stored after parsing; users can delete any analysis or their whole account.

---

## Judge golden path

1. Open the live URL → **Sign up** (or **Continue as guest**).
2. Click **Try Asha's sample** (or upload a resume PDF).
3. See skill chips tagged ▲ rising / ▼ declining (Data Entry shows the ▼ anomaly).
4. Review 3 ranked pathways → open one for the forecast chart, the *"Why this fits you"* panel, and 3 grounded courses.
5. See the 4-agent trace strip.
6. Log out and back in → **My analyses** shows the saved run (re-openable, deletable).
