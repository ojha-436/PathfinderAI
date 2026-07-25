# PathFinder — Plan v2: Demo → Full Working Platform

**Scope of this plan:** take PathFinder from "finalist prototype that works" to a **production-grade consumer platform** by adding three retention-and-guidance features, on top of a hardening layer (migrations, secrets, email, tests, CI/CD, observability).

**The three features (this plan's headline):**
1. **Goal-first reverse roadmap** — *"I want to become X"* → a sequenced, grounded, India-priced learning plan. (Highest value-per-effort; the engine already computes every part.)
2. **Guided interest intake + persona card** — a Career-Dreamer-style branching questionnaire that builds a profile with **no résumé**, unlocking the student segment; ends in a shareable persona card.
3. **Skill timeline + streaks + weekly digest** — turn the transactional tracker into a portal people return to; fixes the retention leak so every other feature compounds.

**Author lens:** senior architect + product designer. **Companion docs:** [plan.md](plan.md) (v1 refinement — largely delivered), [SPEC.md](../SPEC.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [research/COMPETITIVE-ANALYSIS.md](../research/COMPETITIVE-ANALYSIS.md), Notion vault.

---

## 0. Where we are today (already shipped — do not rebuild)

| Area | Status |
|---|---|
| Skill extraction (résumé/text/manual), grounded to 40-skill taxonomy | ✅ Live |
| 5-yr demand forecast (log-linear, deterministic) | ✅ Live |
| 3 ranked career pathways (composite score) | ✅ Live |
| Grounded course rec (free_gov + paid tracks) | ✅ Live |
| Real India job matching (Adzuna primary, JSearch, local fallback) | ✅ Live |
| Learning tracker closed loop + **"✓ Mark complete"** + coverage before→after | ✅ Live |
| Student / Professional personas | ✅ Live |
| Auth: email+password, **Google Sign-In** (needs Client ID), **forgot/reset** (SMTP-pluggable) | ✅ Live (2 env vars pending) |
| Durable persistence: **Cloud SQL Postgres** (pg8000) on Cloud Run | ✅ Live |
| Stable `JWT_SECRET` (persisted `~/.pathfinder/jwt_secret`) | ✅ Live |

**Current data model:** `User(persona)`, `Analysis(*_json blobs)`, `LearningActivity(status, skill_ids, completed_at)`. Progress is **computed on the fly** from completed activities — there is **no snapshot/acquired-skill table yet** (relevant to Feature 3).

---

## 1. Definition of "full working platform" (the demo→prod gap)

A prototype "works in a demo." A platform survives real users, real load, and its own future changes. The gap we are closing:

| Dimension | Demo today | Full platform (target) |
|---|---|---|
| Schema evolution | `Base.metadata.create_all` (won't ALTER live tables) | **Alembic migrations** — versioned, reversible |
| Secrets | Env vars, keys pasted in chat | **Google Secret Manager** + rotation |
| Email | Reset link log-only | **Transactional SMTP** (Brevo/SendGrid/Resend) live |
| Auth | Google code ready, unactivated | Client ID set + origin authorized |
| Tests | Smoke script | **Unit + integration + AI-eval** in **CI (GitHub Actions)** |
| Observability | print/stderr | Structured logs, latency p50/p95, error & cache-hit rates, token spend |
| Abuse/cost control | none | Rate limiting, per-request caps, caches with TTL |
| Retention | transactional (one-and-done) | streaks + timeline + weekly digest loop |
| Legal | account delete exists | privacy policy, terms, consent, data-export |

---

## 2. Design principles (carried forward — non-negotiable)

1. **One engine, many entry points.** Reuse `taxonomy` → `forecast` → `matching.coverage_pct` → `rag.retrieve_courses`. New features are new *entry points and views*, not new engines.
2. **Grounded & deterministic.** Every skill ∈ taxonomy, every course ∈ catalog, every number computed. LLM (Gemini) only **maps free text → taxonomy** and **narrates** computed results — never invents facts. This is the brand; protect it.
3. **India-first outputs.** INR salaries, India job market, free/government course track, Indian education context. Every new surface inherits this.
4. **Pluggable providers + local fallback.** App must run with zero external keys (offline/demo safety).
5. **No open-ended chatbot.** Interactivity comes from **guided/branching flows**, not a free chat that can hallucinate. (Explicit rejection of the Career-Dreamer chat pattern.)

---

## 3. Feature 1 — Goal-first reverse roadmap

**Job-to-be-done:** *"I want to become a Data Analyst — tell me exactly what to learn, in what order, how long, what it costs, and how ready I am at each step."*

**Why cheap:** it **inverts** the existing forward pipeline. `coverage_pct(user_skills, role_id)` and gap-skill logic already exist; we add *sequencing* and a *goal-first entry point*.

### 3.1 Engine (`engines/roadmap.py`)
```
build_roadmap(target_role_id, user_skill_ids) ->
  gap        = role.skills − user_skills                       (existing gap logic)
  for each gap skill: demand = forecast(skill)                 (existing)
                      courses = rag.retrieve_courses(skill)    (existing, free+paid)
                      effort  = sum(course.hours)              (from catalog)
  order gap skills by (prerequisite depth, foundational→advanced, quick-win-first)
  group into phases (≈4–8 wks each); each phase:
      skills[], courses[] (free+paid), est_weeks, project_milestone,
      readiness_after = coverage_pct(user_skills ∪ skills_so_far, role)   ← running %
  return { role, phases[], total_weeks, salary_uplift_inr, readiness_curve[] }
```
- **Sequencing** is deterministic (prerequisite table in taxonomy + difficulty). LLM only writes a one-line rationale per phase (grounded on the computed numbers).
- **Free-text goal** ("I want to work in data") → map to nearest role via taxonomy match, Gemini only as grounded fallback → confirm with the user.

### 3.2 Data model
```
Roadmap(id, user_id→User, target_role_id, goal_text?, source_analysis_id?,
        steps_json, readiness_curve_json, status ENUM(active|archived), created_at)
```
NEW table → `create_all` creates it; **no ALTER needed**. "Adopt roadmap" seeds ordered `LearningActivity` rows (status=saved), so it plugs straight into the existing tracker + Feature 3.

### 3.3 API
```
GET  /api/catalog/roles                 role picker (id, name, INR band, demand)
POST /api/roadmap        { target_role_id | goal_text, analysis_id? | skills? }
                          → { role, phases[], total_weeks, salary_uplift_inr, readiness_curve }
POST /api/roadmap/{id}/adopt             → seeds ordered LearningActivity items
GET  /api/roadmap                        list user roadmaps
```

### 3.4 Frontend (`#/goal`)
Searchable "Become ___" picker → **vertical stepper/timeline**: each phase a card (skills, free+paid courses with ＋Track, est. weeks, project), a running **"You'll be N% ready"** meter, target salary + time-to-ready up top. **"Start this roadmap"** → adopts into My Learning.

**✅ Acceptance:** pick/enter a goal → get an ordered, phase-by-phase plan with rising readiness %, real courses, INR uplift; "Start" populates the tracker in order; deterministic for the same inputs.

---

## 4. Feature 2 — Guided interest intake + persona card

**Job-to-be-done (student):** *"I have no résumé and don't know what I'm good at — ask me questions and point me somewhere."*

### 4.1 Flow (`engines/intake.py`)
- **Branching questionnaire** (server-defined), one question per screen: subjects enjoyed, activities, work-style, constraints, dream field. Each answer option maps to **interest/skill tags** via a curated deterministic table (RIASEC-style scoring).
- Free-text answers → grounded Gemini map to taxonomy (same discipline as résumé extraction).
- Output = the **same `ProfileExtraction` shape** the résumé path produces → runs the **existing analysis pipeline** → stored as an `Analysis` (tagged `source:"guided_intake"` inside `profile_json`, so **no schema change**).

### 4.2 Persona card
- Derived from the analysis: an identity statement ("You're analytical & detail-driven, drawn to data & finance"), top strengths, and 2–3 suggested **India** directions (with demand + INR).
- **Shareable** via an opt-in signed token (reuse the reset-token pattern): `GET /api/card/{token}` returns non-sensitive card data; `#/card/:token` renders a public read-only card (PDF/image export). Privacy: user explicitly chooses to share; card carries no résumé/PII.

### 4.3 API
```
GET  /api/intake/questions          server-defined branching question set
POST /api/analysis/  (extend)        accept intake payload → same pipeline → Analysis
POST /api/card/{analysis_id}/share   → returns a share token (opt-in)
GET  /api/card/{token}               public card data (no PII)
```

### 4.4 Frontend (`#/discover`)
Career-Dreamer-feel guided flow (progress bar, one question per screen) → results → **persona card** with "Share" and "See my pathways / build a roadmap" CTAs (hands off to Feature 1). Onboarding branches on entry: **Student → Discover**, **Professional → résumé/LinkedIn**.

**✅ Acceptance:** a user with no résumé completes the flow → gets grounded pathways + a shareable persona card; all skills/roles ∈ taxonomy; share link renders publicly without exposing PII.

---

## 5. Feature 3 — Skill timeline + streaks + weekly digest (the retention engine)

**Job-to-be-done:** *"Show me my progress over time and keep me coming back."*

### 5.1 Data model (new tables — `create_all`-safe, no ALTER)
```
AcquiredSkill(id, user_id, skill_id, proficiency ENUM(beginner|intermediate|advanced),
              source_activity_id?→LearningActivity, acquired_at)
ProgressSnapshot(id, user_id, analysis_id?, role_id, coverage_pct, taken_at)
UserPrefs(user_id PK→User, weekly_goal_hours, digest_opt_in bool,
          timezone, last_digest_at, streak_weeks, streak_updated_at)
```
On **Mark complete** (existing action): write `AcquiredSkill` rows + one `ProgressSnapshot` per pathway. Timeline reads snapshots (true historical curve, not recomputed against a drifting catalog).

### 5.2 Timeline & streaks
- **Timeline:** chronological skills-acquired + coverage-over-time, rendered with the existing `charts.js` SVG (no new libs). Data already partly exists via `LearningActivity.completed_at`.
- **Proficiency:** replace binary have/don't-have with beginner→advanced (from `AcquiredSkill`), leveled up as more courses in a skill complete.
- **Streaks + weekly goal:** `UserPrefs.weekly_goal_hours`; streak = consecutive weeks the goal was met (derived from completion timestamps). Streak badge + goal ring in My Learning.

### 5.3 Weekly digest (reuses the SMTP infra from reset-email)
- **Cloud Scheduler → Cloud Run job** (or a protected `POST /internal/digest/run`) weekly: for each opted-in user, compose a **grounded** digest — new India jobs matching them, forecast shifts on their skills, streak status, "2 courses from your goal" — and send via SMTP. Opt-in only; every email has unsubscribe.

### 5.4 API
```
GET  /api/timeline                acquired skills + coverage snapshots over time
GET  /api/streak                  current streak + weekly-goal progress
GET/PUT /api/prefs                weekly goal, digest opt-in, timezone
POST /internal/digest/run         scheduler-triggered (auth: OIDC/service token)
```

**✅ Acceptance:** completing courses populates a visible timeline + rising proficiency; streak increments across weeks; opted-in users receive a correct, grounded weekly email; all content traceable to real data.

---

## 6. Production-hardening workstream (parallel to features)

| # | Item | Detail |
|---|---|---|
| H1 | **Alembic migrations** | Replace reliance on `create_all` for schema change. `create_all` **does not ALTER** existing live tables — every new column (and clean table versioning) needs a migration. Add `alembic`, autogenerate, run on deploy. **Blocks Features 1 & 3 tables on live Postgres.** |
| H2 | **Secret Manager + rotation** | Move `GEMINI_API_KEY`, `RAPIDAPI_KEY`, `ADZUNA_*`, `JWT_SECRET`, SMTP creds into Secret Manager; `--set-secrets`. Rotate the pasted keys. |
| H3 | **Email live** | Wire transactional SMTP (Brevo recommended) → reset + digest emails actually send. |
| H4 | **Google Sign-In activation** | Set `GOOGLE_CLIENT_ID`; authorize JS origin `https://pathfinder-823065407403.asia-south1.run.app`. |
| H5 | **Testing + CI** | pytest: matching math, roadmap sequencing, intake mapping, streak logic, digest composer (mocked SMTP), auth flows. **AI-eval:** grounding audit (every emitted skill/course ∈ catalog), determinism. GitHub Actions → Cloud Run on green. |
| H6 | **Observability** | Structured JSON logs → Cloud Logging; latency p50/p95 on heavy routes; provider error rates; Gemini token spend; cache hit-rate. |
| H7 | **Abuse & cost control** | Rate-limit auth + analysis + roadmap; cap Gemini calls/request; caches (job, JD-parse) with TTL; prompt-injection guard on all free-text→Gemini. |
| H8 | **Legal/consent** | Privacy policy, terms, cookie/consent, data-export (account delete already exists). |
| H9 | **Mobile/PWA + a11y** | India is mobile-first: installable PWA, responsive audit, WCAG AA pass. |

---

## 7. Consolidated data-model changes

New tables (all `create_all`-safe, but introduce via **Alembic** for production correctness):
`Roadmap`, `AcquiredSkill`, `ProgressSnapshot`, `UserPrefs`, optional `SharedCard(token, analysis_id, created_at)`.
No changes to existing `User` / `Analysis` / `LearningActivity` columns (intake stores its source inside `profile_json` to avoid an ALTER). New curated data (optional): `data/prerequisites.json` (skill ordering for roadmap sequencing) and `data/programs.json` (higher-ed, if Theme D is picked up later).

---

## 8. Phased delivery (with acceptance criteria)

> Sequence rationale: **hardening that unblocks (H1) first**, then the highest-leverage feature, then the retention loop that makes the rest compound.

**Phase 0 — Migration & secrets foundation (1–2 days)**
- H1 Alembic + baseline migration; H2 Secret Manager; H3 SMTP live; H4 Google Client ID.
- ✅ *Accept:* a new column/table deploys via migration (not create_all); reset email actually arrives; Google button works live.

**Phase 1 — Goal-first reverse roadmap (3–4 days)**
- `engines/roadmap.py`, `Roadmap` table, endpoints, `#/goal` stepper UI, adopt→tracker.
- ✅ *Accept:* goal → sequenced plan with rising readiness %, real courses, INR uplift; adopt seeds tracker in order.

**Phase 2 — Guided intake + persona card (3–4 days)**
- `engines/intake.py`, question set, pipeline reuse, persona card + opt-in share.
- ✅ *Accept:* no-résumé user gets grounded pathways + shareable card; branched onboarding.

**Phase 3 — Timeline + streaks + digest (3–4 days)**
- `AcquiredSkill`/`ProgressSnapshot`/`UserPrefs`, timeline chart, streaks, Cloud Scheduler digest.
- ✅ *Accept:* visible timeline + proficiency; streak across weeks; correct grounded weekly email to opted-in users.

**Phase 4 — Harden & ship (2–3 days)**
- H5 tests+CI, H6 observability, H7 rate-limit/cache, H8 legal, H9 PWA/a11y.
- ✅ *Accept:* CI green on PR; dashboards show latency + cache hit-rate; rate limits enforced; privacy/terms live; Lighthouse PWA + a11y pass.

**Recommended order:** 0 → 1 → 3 → 2 → 4. (Roadmap is the hero; the retention loop (3) should land early so intake-driven students (2) don't leak away.)

---

## 9. Success metrics (how we know "full platform" worked)

- **Activation:** % of new users who reach a first result (résumé *or* guided intake).
- **Retention (north star):** W1/W4 return rate; % who complete ≥1 tracked course; streak distribution.
- **Guidance value:** % who adopt a roadmap; readiness-% delta per active user.
- **Trust/quality:** grounding-audit pass rate (target 100% — zero out-of-catalog emissions); JD/intake mapping precision.
- **Reliability/cost:** p95 latency on `/roadmap` & `/jobs/match`; Gemini spend/user; cache hit-rate; error rate.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Live schema drift** (create_all won't ALTER) | Alembic in Phase 0 *before* any new column/table hits prod |
| Free-text goal/intake mis-mapping | Deterministic tables first; Gemini grounded fallback; always confirm the mapped role with the user |
| Chatbot scope-creep undermining grounding | Guided/branching flows only; LLM restricted to map+narrate |
| Digest = spam/deliverability | Opt-in, unsubscribe, transactional provider, frequency cap |
| Scope (3 features + hardening) for a small team | Strict phase gates; ship Phase 1 end-to-end before Phase 2; personas share one engine |
| Cost blow-up (Gemini/job APIs) | Caches + per-request caps + local fallback; watch token spend metric |
| Persona card leaking PII | Card carries only non-sensitive summary; opt-in signed token; no résumé text |

---

## 11. Config / decisions needed from you

- **Google OAuth Client ID** (+ authorize the JS origin) — activates Sign-In.
- **Transactional email creds** (Brevo/SendGrid/Resend SMTP) — activates reset + digest.
- **Primary user for the next cycle:** ✅ **Both equally** (decided). The recommended order already balances this — *roadmap* (Phase 1) and *timeline+streaks* (Phase 3) are persona-neutral and serve both; *guided intake* (Phase 2) adds the student on-ramp; the existing job-matching covers professionals. **Anti-dilution rule:** ship each phase end-to-end (one engine, both lenses) before starting the next — do **not** fork into parallel student/professional tracks.
- **Higher-education pillar (Theme D)** — in/out of this cycle? (Needs a maintainable, citable India education dataset before it can ship grounded.)
- **Budget** for always-on Cloud Run + Gemini + Cloud Scheduler.

---

*This plan extends, and does not replace, [plan.md](plan.md) (v1 refinement, delivered). All new work preserves the grounded, India-first, one-engine architecture.*
