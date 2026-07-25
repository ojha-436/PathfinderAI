# PathFinderAI — Architecture & Tech-Stack Graph

> This graph maps every component, the data flow between them, and the technology behind each. It renders on GitHub and in Notion. Companion: [SPEC.md](../SPEC.md) · [ARCHITECTURE.md](../ARCHITECTURE.md) · [README.md](README.md).

## Architecture & data-flow graph

```mermaid
flowchart LR
  %% ---------- Inputs ----------
  subgraph IN[" Inputs "]
    R["Resume PDF<br/><i>pypdf</i>"]
    C["Connectors<br/>LinkedIn · Indeed · Naukri"]
    M["Paste / Manual skills"]
  end

  %% ---------- Client ----------
  SPA["Web SPA<br/><i>HTML · CSS · vanilla JS · SVG charts</i><br/>landing · auth · analyze · history"]

  %% ---------- Cloud Run app ----------
  subgraph CR[" Google Cloud Run · Docker · Python 3.11 "]
    API["FastAPI + Uvicorn<br/><i>JSON API /api + static SPA /</i>"]
    AUTH["Auth<br/><i>JWT HS256 + PBKDF2</i>"]
    subgraph ORCH[" 4-Agent Orchestrator · ADK-shaped "]
      A1["1 · SkillsExtractor"] --> A2["2 · MarketAnalyst"] --> A3["3 · PathwayPlanner"] --> A4["4 · ROIForecaster"] --> A5["5 · CourseGrounder"]
    end
  end

  %% ---------- Pluggable AI providers ----------
  subgraph PROV[" Pluggable AI providers  (⇄ local fallback) "]
    G["Gemini 2.5-flash<br/><i>skill extraction (grounded)</i>"]
    V["Vertex AI RAG<br/><i>course grounding</i>"]
    B["BigQuery + BQML<br/><i>ML.FORECAST demand</i>"]
    LG["local extractor"]:::local
    LV["local retrieval"]:::local
    LB["local log-linear model"]:::local
  end

  %% ---------- Data ----------
  subgraph DATA[" Data "]
    DB[("Persistence · SQLAlchemy<br/>SQLite → Cloud SQL / AlloyDB<br/><i>Users · Analyses (JSON)</i>")]
    DS[("Curated datasets<br/><i>skills(40) · demand series · role–skill<br/>salaries · courses(57, free/paid)</i>")]
  end

  %% ---------- Edges ----------
  R --> SPA
  C --> SPA
  M --> SPA
  SPA -->|HTTPS + JWT| API
  API --> AUTH
  API --> ORCH
  AUTH --> DB
  API -->|save / read analyses| DB
  A1 -.-> G --- LG
  A2 -.-> B --- LB
  A5 -.-> V --- LV
  ORCH -->|reads| DS
  API -.->|/api/health shows active provider| PROV

  classDef local fill:#eee,stroke:#999,color:#555,font-size:10px;
```

## Technology stack (by layer)

| Layer | Technology |
|---|---|
| **Frontend** | HTML5 · CSS3 (custom design system) · vanilla ES modules · hand-rolled SVG charts (no build step) |
| **Backend / API** | Python 3.11 · FastAPI · Uvicorn (ASGI) · Pydantic v2 · python-multipart |
| **Auth** | JWT (HS256) + PBKDF2-HMAC-SHA256 (stdlib only) |
| **AI — extraction** | Google **Gemini** `gemini-2.5-flash` (`google-generativeai`) ⇄ local taxonomy extractor |
| **AI — grounding** | **Vertex AI RAG** ⇄ local catalog retrieval |
| **AI — forecasting** | **BigQuery + BQML** `ML.FORECAST` (ARIMA_PLUS) ⇄ local log-linear model |
| **Orchestration** | Native 4-agent orchestrator + **ADK** `SequentialAgent` harness |
| **Parsing / docs** | pypdf (resume) · python-pptx (deck) |
| **Persistence** | SQLAlchemy ORM · SQLite (dev) → Cloud SQL / AlloyDB Postgres (prod) |
| **Data** | Curated JSON datasets (skills, demand series, role–skill matrix, salaries, courses) |
| **Infra / deploy** | Docker · **Google Cloud Run** · Cloud Build (project `promptwar-501405`, `asia-south1`) |
| **Live** | https://pathfinder-383713992026.asia-south1.run.app/#/ |

## Component legend

- **SkillsExtractor** — resume/profile → canonical skill IDs (Gemini, grounded to the taxonomy).
- **MarketAnalyst** — 3-year demand forecast per skill (rising ▲ / declining ▼).
- **PathwayPlanner** — profile × role–skill matrix → candidate roles by weighted coverage.
- **ROIForecaster** — ranks top 3 by composite score (coverage × demand × uplift × achievability); quantifies payoff.
- **CourseGrounder** — grounded courses per pathway in two tracks (Free Govt/YouTube · Paid).

*Pluggable-provider pattern: every AI capability runs on a deterministic local implementation by default and upgrades to the Google Cloud service when its env var is set — the app is fully functional with zero cloud credentials and never breaks (providers fail-open to local).*
