# PathFinder — Refinement Plan

**Scope:** persona-split dashboards (Student / Professional), a **learning-activity tracker with a closed re-assessment loop**, and a **"real jobs matched to me"** engine sourced from *compliant, verified* job APIs (never scraping LinkedIn/Indeed).
**Author lens:** senior architect + software engineer. **Branch:** `finaliseapp`. **Status:** Top-101 finalist → productionizing.
**Companion docs:** [SPEC.md](../SPEC.md) · [ARCHITECTURE.md](../ARCHITECTURE.md) · [ARCHITECTURE_GRAPH.md](ARCHITECTURE_GRAPH.md) · Notion Refinement Vault.

---

## 1. Design principles (non-negotiable)

1. **One engine, two lenses.** Keep the existing pipeline (extract → forecast → pathways → ground). Personas change *output emphasis + one new input (jobs)*, not the core. Do not fork into two apps.
2. **Pluggable providers with local fallback.** Every external dependency (jobs, Gemini, forecast) sits behind an interface with a deterministic local implementation, exactly like today. The app must still run with zero external keys (offline demo safety).
3. **Compliant by construction.** No scraping of LinkedIn/Indeed/company sites. Jobs come from licensed aggregator APIs + official ATS board APIs. We *deep-link* to the original posting; we never auto-apply.
4. **Explainable & grounded.** Every job match shows *match %, matched skills, gap skills, and courses to close them* — traceable numbers, not vibes. The LLM narrates; it never invents figures.
5. **Cache aggressively.** External calls and Gemini JD-parses are cached (cost + latency + reproducibility).

---

## 2. Technology & API decisions

### 2.1 Job data sources — **DECISION**

| Source | Role in system | Why | Verdict |
|---|---|---|---|
| **JSearch (RapidAPI)** | **Primary** live search | Aggregates **Google for Jobs**, which itself indexes LinkedIn, Indeed, Glassdoor, ZipRecruiter — so we deliver the "LinkedIn/Indeed" coverage the vision wanted, *compliantly*, via one REST call. Good India coverage, simple `/search` + `/job-details`. | ✅ **Chosen (primary)** |
| **Adzuna API** | **Secondary** + salary data | Official developer API, strong **India** coverage, returns **salary bands** (feeds our ROI numbers), stable free tier. Great cross-check + fallback if JSearch quota hits. | ✅ **Chosen (secondary)** |
| **Greenhouse & Lever public board APIs** | **"Verified employer" set** | Postings **straight from the company's ATS** (`boards-api.greenhouse.io/v1/boards/{token}/jobs`, `api.lever.co/v0/postings/{co}`). No key, no ToS issue. This is literally "company recruitment website" data — the most verified tier. Curate ~20–30 target employers. | ✅ **Chosen (verified tier)** |
| **Local sample jobs** (`data/jobs_sample.json`) | Offline/demo/tests | Deterministic fallback so the app + judges work with zero keys. | ✅ **Chosen (fallback)** |
| **Google Cloud Talent Solution** | Scale-up matching | GCP-native job search/ranking — but requires ingesting & owning a job **corpus** (tenants/companies/jobs). Overkill for live shortlist matching; our own skill-overlap matching is more explainable and on-brand. | ⏸️ **Deferred** (note as scale path; good GCP story later) |
| India **NCS** (National Career Service) | Govt/verified | No clean public API; needs partnership. | ⏸️ **Deferred** |
| Scraping LinkedIn / Indeed / all sites | — | ToS violation, active blocking, unmaintainable. | ❌ **Rejected** |

**Net:** JSearch (breadth incl. LinkedIn/Indeed via Google for Jobs) + Adzuna (India + salary) + Greenhouse/Lever (verified-from-employer) + local sample. All behind one `JobProvider` interface.

### 2.2 Matching & AI

- **JD → skills:** **Gemini `gemini-2.5-flash` structured output** parses each job description into our canonical 40-skill taxonomy (grounded — no invented skills). Cached by JD hash.
- **Match scoring:** **in-app**, reusing the existing weighted-overlap logic (`agents/orchestrator.py`) — `match% = weighted(user_skills ∩ job_required_skills)`, plus `gap_skills`. Explainable and consistent with pathway scoring. (This is why we don't need Cloud Talent Solution yet.)
- **Gap → courses:** reuse `engines/rag.retrieve_courses()` on the gap skills (Free/Paid tracks already built).
- **Narration (P1):** Gemini writes a one-line "why you're a fit / what's missing" grounded strictly on the computed numbers.

### 2.3 Platform / stack additions (on top of current FastAPI + SQLAlchemy + Gemini + Cloud Run)

| Concern | Choice | Rationale |
|---|---|---|
| Durable persistence | **Cloud SQL Postgres** via SQLAlchemy (`pg8000` driver) | Tracker + job cache must survive redeploys; SQLite (current) resets. One `DATABASE_URL` change. |
| Async HTTP | **httpx.AsyncClient + asyncio** | Fan out job fetch + concurrent JD parses; keep p95 low. |
| Caching | **Postgres cache tables** (`job_cache`, `jd_parse_cache`) with TTL | Cost control (Gemini + API quotas), latency, reproducibility across instances. |
| Secrets | **Google Secret Manager** | `RAPIDAPI_KEY`, `ADZUNA_APP_ID/KEY`, `GEMINI_API_KEY`, `JWT_SECRET`. Rotate the shared Gemini key here. |
| Scheduled refresh (P1) | **Cloud Scheduler → Cloud Run job** | Warm the verified-employer (Greenhouse/Lever) cache nightly. |
| Frontend | Keep **vanilla-JS SPA** (no build step) | Add persona toggle + two dashboard views + tracker + job cards. Consistent, OneDrive-safe. |

---

## 3. Data model changes (SQLAlchemy → Postgres)

```
User            + persona ENUM(student|professional) default from years_experience
                + location (str, nullable)  + target_role (str, nullable)
AcquiredSkill   (id, user_id→User, skill_id, source_item_id, acquired_at)   # what they've learned
LearningActivity(id, user_id→User, item_type ENUM(course|program),
                 ref_id, pathway_id, title, skill_ids JSON,
                 status ENUM(saved|in_progress|completed), created_at, completed_at)
ProgressSnapshot(id, user_id→User, pathway_id, match_pct, taken_at)         # for the "42%→61%" chart
JobCache        (id, query_hash, source, payload JSON, fetched_at)          # TTL
JDParseCache    (id, jd_hash, skill_ids JSON, model, parsed_at)             # TTL, cost control
```
Curated data file: **`data/programs.json`** (higher-studies: diplomas / bachelor / master / PG-cert; fields: id, title, institution, level, mode, duration, cost, url, skills[]). Loaded like `courses.json`.
Trending skills need **no schema change** — computed from the forecast engine (top rising by `growth_rate_annual`).

---

## 4. New backend modules & endpoints

**Modules** (extend the existing `engines/` + `agents/` pattern):
```
engines/jobs.py       Job schema · JobProvider ABC · JSearchProvider · AdzunaProvider ·
                      AtsProvider(Greenhouse/Lever) · LocalSampleProvider · get_job_provider()
engines/jd_parser.py  Gemini JD→canonical skill_ids (grounded) + JDParseCache
engines/matching.py   match(user_skills, required_skills) → {pct, matched, gaps}  (shared w/ pathways)
engines/programs.py   loader for programs.json (higher studies)
agents/job_matcher.py     professional final step: fetch → parse → match → gap→courses → rank
agents/study_planner.py   student final step: courses + programs + trending → sequenced plan
services/learning.py      tracker CRUD + closed-loop re-forecast on completion
routers/jobs.py · routers/learning.py · routers/dashboard.py · routers/catalog.py(+programs,+trending)
```

**API surface (new/changed):**
```
PATCH  /api/auth/me                 { persona, location?, target_role? }
GET    /api/dashboard               persona-aware summary (student | professional)
POST   /api/jobs/match              { analysis_id | profile, location?, limit? }
                                    → [{ job, source, match_pct, matched_skills, gap_skills,
                                         courses_for_gaps[], apply_url }]
GET    /api/trending?domain=        top rising skills (from forecast)
GET    /api/programs                higher-studies catalog (student)
GET    /api/learning                user's tracked items
POST   /api/learning               add { item_type, ref_id, pathway_id }
PATCH  /api/learning/{id}           { status }  → on 'completed': acquire skills + re-forecast
GET    /api/progress               pathway match_pct over time (ProgressSnapshot)
```

---

## 5. The three flows

### 5.1 Professional — "real jobs matched to me"
```
profile.skills + top pathways + location
  → JobProvider.search(role/keywords, location)         # JSearch primary, Adzuna+ATS merge, dedupe
  → for each job (async, capped ~15): jd_parser → required skill_ids   [cache by jd_hash]
  → matching.match(user_skills, required)   → match_pct, matched, gaps
  → rag.retrieve_courses(gaps)              → courses to qualify
  → rank by match_pct (tie: recency, salary) → top N
  → each card: title · company · location · salary · match% · matched/gap chips ·
               "learn these to qualify" courses · Apply (deep-link to source)
```

### 5.2 Student — courses + higher studies + trending
```
profile.skills + pathways
  → courses (rag, Free/Paid)  +  programs.json (matched to skills/pathway)
  → trending = forecast top-rising skills in domain
  → study_planner: sequence into a term-by-term plan tied to the tracker
```

### 5.3 Learning tracker — the closed loop (the retention engine)
```
recommend course/program → user saves → marks in_progress → marks completed
  → AcquiredSkill += course.skills
  → re-run forecast + pathway match on (profile.skills ∪ acquired)
  → write ProgressSnapshot → UI shows delta ("Data Analyst match 42% → 61%; 2 of 5 gaps closed")
```
This works identically for both personas and is 100% internal (zero external risk).

---

## 6. Frontend changes (vanilla-JS SPA)

- **Persona toggle** in the header (defaults from profile; remembered on User).
- **Dashboard view** (`#/dashboard`) that renders Student *or* Professional layout from `/api/dashboard`.
- **Professional:** job-match cards (match ring, matched/gap chips, gap-courses, Apply link, source badge).
- **Student:** courses (Free/Paid) + higher-studies program cards + "Top rising skills" panel + study plan.
- **Tracker:** "My Learning" — saved/in-progress/done, and a **progress chart** (pathway match over time) reusing the existing SVG chart code.

---

## 7. Phased delivery (with acceptance criteria)

**Phase 0 — Foundations (1–2 days)**
- Cloud SQL Postgres (`DATABASE_URL` + `--add-cloudsql-instances`, add `pg8000`); Secret Manager; `.gitignore` + untrack venv/db; add `httpx`.
- ✅ *Accept:* app runs on Postgres; accounts/history survive a redeploy; secrets not in source.

**Phase 1 — Jobs feed spike / de-risk (2 days)**
- `engines/jobs.py` + JSearchProvider + LocalSampleProvider + normalize + dedupe; `/api/jobs/match` returns raw jobs (no matching yet).
- ✅ *Accept:* real India jobs returned for a role+location; offline fallback works with no keys.

**Phase 2 — Job matching (2–3 days)**
- `jd_parser.py` (Gemini structured, cached) + `matching.py` + gap→courses; full `/api/jobs/match`; professional dashboard UI.
- ✅ *Accept:* each job shows match %, matched + gap skills, and courses; deterministic given cache; Apply deep-links to source.

**Phase 3 — Learning tracker closed loop (2 days)**
- Tables + `services/learning.py` + endpoints + re-forecast + progress chart.
- ✅ *Accept:* complete a course → target pathway match visibly increases; persists across sessions.

**Phase 4 — Student dashboard (2 days)**
- `programs.json` + `engines/programs.py` + trending + `study_planner`; student UI.
- ✅ *Accept:* student sees courses + real programs + top rising skills + a sequenced plan.

**Phase 5 — Persona routing, eval, CI/CD, deploy (2 days)**
- Persona toggle + `/api/dashboard`; AI eval harness (JD-parse accuracy, match sanity, hallucination audit); pytest + GitHub Actions → Cloud Run; redeploy.
- ✅ *Accept:* both dashboards live; tests green in CI; eval report generated.

---

## 8. Caching, cost & rate limits

- **JDParseCache** by SHA-256 of JD text → skip Gemini on repeats (biggest cost lever).
- **JobCache** by (query, location, source) with 6–24h TTL.
- Cap JDs parsed per request (~15); paginate the rest.
- Per-provider rate-limit guard + graceful fallback JSearch → Adzuna → local.
- Nightly **Cloud Scheduler** warm-up for the verified-employer (ATS) set.

## 9. Security & compliance

- Keys in **Secret Manager**; **rotate the shared Gemini key** immediately.
- Deep-link to original postings only; **no auto-apply**, no credential storage.
- Respect each provider's ToS/attribution (JSearch/Adzuna require source attribution — show "via Adzuna/Google Jobs").
- Treat resume/JD text as **data** (prompt-injection guard) in all Gemini calls.
- Rate-limit auth + match endpoints; refresh-token rotation (P1).

## 10. Testing & eval

- **Unit:** matching math, JD parser (mocked Gemini), providers (mocked HTTP).
- **Integration/E2E:** `/api/jobs/match`, tracker loop, dashboard per persona (pytest + httpx).
- **AI eval harness:** golden JDs → expected skills (precision/recall); match-score sanity; zero-hallucination audit (every course/skill ∈ taxonomy/catalog); determinism with cache warm.
- Extend existing `tests/smoke_pipeline.py`.

## 11. Observability & deployment

- Structured logs + Cloud Logging/Trace; latency (p50/p95) on `/api/jobs/match`; provider error rates; cache hit-rate; Gemini token spend.
- Cloud Run: min-instances 1 warm, tuned concurrency, gzip; Cloud SQL connector.
- Blue-green via revisions; staging service before promote.

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Job API quota/cost | Cache hard; Adzuna+local fallback; cap parses/request |
| JD-parse accuracy | Grounded structured output + eval harness + gap review |
| Persona mis-assignment | Toggle (not a wall); default from profile, user-overridable |
| Postgres migration effort | SQLAlchemy already abstracts it; do in Phase 0; keep SQLite for local |
| Scope creep (two dashboards) | One engine + lenses; ship Professional first (finals hero), Student next |

## 13. Config needed from you

- **RapidAPI key** (JSearch) and **Adzuna** `app_id`/`app_key` (both free tiers).
- Cloud SQL: confirm **Cloud SQL vs AlloyDB** + budget for always-on Cloud Run + Gemini/BQML.
- Target **verified-employer list** for Greenhouse/Lever (which companies to feature).
- Primary market/location default (e.g., India / specific cities).

---

### Recommended build order for the finals
**Phase 0 → 1 → 2** (professional "real jobs matched to me" is the demo hero) **→ 3** (tracker loop = the retention wow) **→ 4 → 5**. Ship the Professional dashboard end-to-end before starting Student.
