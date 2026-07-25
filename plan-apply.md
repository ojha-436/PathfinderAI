# PathFinderAI — Plan: Apply Assistant ("Apply once, apply everywhere")

**Value proposition:** *Turn a 20-minute application into a 2-minute review.*
Upload your résumé once → PathFinderAI builds a structured, editable master profile → paste a job → get a grounded, ATS-friendly résumé + tailored cover letter + suggested answers → review → (with the browser extension) auto-fill and submit yourself.

**One profile, two superpowers:** the same master profile feeds **Grow** (the existing roadmap/forecast) and **Apply** (this). That integration — honest tailoring *plus* an honest match/gap read — is the wedge no auto-apply tool has.

**JTBD:** *When I'm applying to many jobs, I want to stop re-entering the same info and re-tailoring from scratch, so I can send more, better-targeted applications in less time — without lying.*

---

## 1. Non-negotiable principles

1. **Zero fabrication.** Generators (résumé/cover letter/answers) may reword, reorder, and emphasize — but **never invent** an employer, title, date, degree, or metric. A verification step rejects any factual claim not present in the master profile. (This is both the ethic and the brand.)
2. **Compliant by construction.** No scraping of LinkedIn/Indeed/Workday. JD comes from pasted text (always) or a best-effort fetch of *public/ATS* pages (Greenhouse/Lever/company career pages).
3. **Human-in-the-loop submit.** We generate and (via the extension) fill; **the user reviews and clicks submit.** No auto-submit — ever.
4. **PII-careful.** The master profile is sensitive (phone, address, full history). Own-user access only, encryption at rest (Cloud SQL), never logged, deletable with the account.
5. **Grounded + reusable.** Built on the existing stack (FastAPI + Postgres + Gemini + vanilla-JS SPA + Cloud Run + Alembic), reusing `jd_parser`, `matching`, and the provider/grounding patterns.

---

## 2. Feasibility (honest, tiered)

| Capability | Verdict | Notes |
|---|---|---|
| Master profile (upload once → editable sections) | ✅ Build now | Extends résumé parsing; pure web-app |
| Paste JD → match + ATS résumé + cover letter + Q&A | ✅ Build now | Reuse jd_parser + matching + Gemini (grounded) |
| Paste *any* job URL → auto-extract JD | ⚠️ Limited | Paste-text always; URL fetch only for public/ATS pages. LinkedIn/Indeed/Workday blocked (ToS/JS) |
| Auto-fill repetitive fields | 🧩 Needs extension | A web app can't fill third-party forms (cross-origin) → Chrome MV3 extension, Phase C |
| Auto-submit | 🚫 Out of scope | ToS/CAPTCHA/ethics — user submits after review |

---

## 3. The Master Profile (Phase A — the keystone)

Upload résumé once → Gemini (grounded to the résumé text) extracts an **ordered list of typed, editable sections**. Every section and entry is **editable**, **reorderable**, **deletable**, and the user can **add custom sections**.

Default sections (auto-detected from the résumé; absent ones simply don't appear):
- **Personal** — name, headline, email, phone, location, links (LinkedIn/GitHub/portfolio)
- **Summary / Objective**
- **Education** — degree, institution, year, score
- **Experience** — title, org, dates, bullet points
- **Projects** — name, description, tech, link
- **Certifications** — name, issuer, year, credential link
- **Hackathons / Competitions** — name, result, year, description
- **Skills** — grounded to the taxonomy *plus* free-text skills the résumé lists
- **Achievements / Awards**, **Publications**, **Volunteering**, **Languages**
- **+ Custom section** — user-named, free-form entries

Stored as flexible JSON (so custom sections "just work") with a stable schema per section type. This profile becomes the single source of truth for every generated document, and also an alternate input to the existing analysis/roadmap.

**✅ Accept:** upload a résumé → see it split into correct, editable sections; edit/add/reorder/delete sections and entries; it persists; account-delete removes it.

---

## 4. Apply Studio (Phase B)

```
master profile + (pasted JD text | fetched public JD)
  → jd_parser: JD → required skills + parsed requirements
  → matching: match % + matched/gap skills (reuses existing engine)
  → apply_gen (Gemini, GROUNDED to profile):
       • ATS résumé   (reorder/emphasize real experience toward the JD keywords)
       • cover letter (profile facts only)
       • answers to pasted screening questions
  → grounding check: every emitted employer/title/date/degree ∈ master profile, else flag/strip
  → review screen: edit anything → download (ATS-clean PDF/TXT) / copy
  → Application tracker: job, company, match %, status (draft/generated/applied), generated docs
```

**ATS-friendly output = concrete rules:** single column, standard section headings, no tables/text-boxes/images/icons, standard fonts, JD-keyword alignment, plain reverse-chronological structure. (Fancy résumés fail ATS parsers.) Export as ATS-clean HTML → browser "Download PDF", plus a copy-as-text; DOCX later.

**✅ Accept:** paste a JD → get a match %, a tailored ATS résumé + cover letter + answer drafts that contain **only** facts from the profile; edit + download; the application is saved to the tracker.

---

## 5. Browser extension (Phase C — separate track)

A Chrome MV3 extension is the only compliant way to auto-fill third-party forms.
- Content script detects form fields on a job page; maps them to master-profile values via the PathFinderAI API (user's token).
- Surfaces the generated résumé/cover letter/answers for the current JD.
- Fills fields → **user reviews → user clicks submit.** No auto-submit.
- Popup: login, pick which profile/answers, one-click fill.

**✅ Accept:** on a supported ATS form, one click fills name/email/phone/education/experience + suggested answers; user edits and submits.

---

## 6. Data model (Alembic; new tables)

```
Profile          user_id (1:1 FK), sections_json (ordered typed sections),
                 full_name, email, phone (convenience columns), updated_at
Application      id, user_id FK, company, job_title, job_url?, jd_text,
                 jd_skills_json, match_json, status(draft|generated|applied),
                 created_at, updated_at
GeneratedDoc     id, application_id FK, kind(resume|cover_letter|answers),
                 content_json, format, created_at   # versioned per application
AnswerBank       id, user_id FK, question, answer, updated_at   # Phase D: remembered answers
```
`sections_json` keeps custom sections trivially flexible; convenience columns are for fast autofill lookups. All FKs `ON DELETE CASCADE` + ORM relationships (account-delete wipes everything).

---

## 7. API surface (new)

```
# Profile (Phase A)
POST /api/profile/from-resume     upload résumé (PDF/text) → structured sections (draft, not saved for guests)
GET  /api/profile                 the user's master profile
PUT  /api/profile                 replace/patch sections (edit/add/reorder/delete)

# Apply Studio (Phase B)
POST /api/apply/extract           { url | jd_text } → { jd_text, skills, match }
POST /api/apply/generate          { application_id|jd, kinds:[resume,cover_letter,answers], questions? }
GET  /api/apply                   list applications (tracker)
POST /api/apply                   create/save an application
GET  /api/apply/{id}              application + generated docs
GET  /api/apply/{id}/export?kind=resume&fmt=pdf|txt   ATS-clean download
```

---

## 8. Phased delivery + acceptance

| Phase | Scope | Accept |
|---|---|---|
| **A — Master Profile** | `engines/profile_builder.py`, `Profile` table + migration, `routers/profile.py`, `#/profile` builder UI (upload → editable sections, add custom) | Upload → correct editable sections; persists; deletable |
| **B — Apply Studio** | `engines/jd_extract.py` + `apply_gen.py` (grounded), `Application`/`GeneratedDoc` tables, `routers/apply.py`, `#/apply` (paste JD → match + docs → review → export) + tracker | Grounded résumé/CL/answers from profile only; download; tracked |
| **C — Extension** | Chrome MV3 (content script + popup) hitting the profile API; auto-fill; user submits | One-click fill on a supported ATS form |
| **D — Polish** | DOCX export, multiple ATS templates, AnswerBank memory, apply analytics | — |

Recommended: ship **A** first (independently useful + everything depends on it), then **B**, then decide on **C** based on demand.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Fabricated experience** (ethical + trust) | Grounding verifier: emitted facts must ⊆ profile; Gemini told to reword-not-invent; user reviews before use |
| "Any URL" over-promise | Paste-text primary; URL fetch only public/ATS; clear messaging; never scrape ToS-protected sites |
| Auto-fill expectations | Extension is Phase C + clearly separate; web app delivers docs + copyable data meanwhile |
| Auto-submit | Explicitly out of scope; human submits |
| PII exposure | Own-user access, encryption at rest, no PII logging, cascade delete, privacy-policy update |
| ATS parser failures | Strict ATS format rules; text export option; test against a real parser |
| Gemini latency/cost on generate | One structured call per doc, cached per (profile-version, jd-hash); reuse thinking-model lesson (no tiny max_output_tokens) |

---

## 10. Success metrics

- **Time-to-application** (target: <2 min from JD → ready-to-submit package)
- **Applications/user/week** (throughput lift)
- **Profile completion rate** (% who finish the master profile after upload)
- **Grounding audit pass rate** (target 100% — zero fabricated facts in generated docs)
- **Doc edit rate** (how much users change the AI draft — proxy for quality)

---

## 11. Decisions needed from you

- **Primary user for v1** — ✅ **Both (balanced)** (decided): auto-detect sections from the résumé and show whichever apply; balance answer-help (students/freshers) with experience-tailoring + ATS keyword alignment (professionals).
- **Export format priority** — PDF (print) first, or DOCX (needs `python-docx` dep)?
- **Extension now or later** — build Phase C, or validate A+B first?
- **Data retention** — how long to keep pasted JDs / generated docs (privacy)?

*Companion: [ARCHITECTURE-apply.md](ARCHITECTURE-apply.md). Fits the existing stack in [ARCHITECTURE.md](../ARCHITECTURE.md); reuses the grounded/Gemini patterns from [plan-v2.md](plan-v2.md).*
