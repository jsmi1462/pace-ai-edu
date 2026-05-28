# Pace AI Edu — Unified Project Map & Task Assignments

## North Star

Each Pace Academy teacher logs into a zero-friction dashboard (email = identity), sets up their
profile once, and receives a personalized digest — 3–5 articles from educational research,
each translated into:

1. A two-sentence summary of the core concept  
2. Three actionable classroom steps they can take **tomorrow**  
3. One sentence connecting the research to the **Pace Academy mission**  

Output is calibrated to their **discipline**, **current module/unit**, **years of experience**,
and self-described **tailoring query**.

**Timeline: 48-hour proof-of-concept demo.**

---

## Resolved Design Decisions

| Question | Decision | Source |
|---|---|---|
| LLM provider | Local LM Studio / MLX on Mac Mini (zero-cost) | Gemini |
| Article sources (v1) | RSS scraping — Cult of Pedagogy, MiddleWeb, TeachThought | Gemini |
| Delivery mechanism | React dashboard served by Express | Gemini/Claude |
| Auth | Cloudflare Zero Trust → `@paceacademy.org` only (needs domain); DEV_EMAIL fallback for demo | Gemini |
| Compute | M4 Mac Mini (48GB) on-premises via Tailscale + Cloudflare Tunnel | Gemini |
| Output format | 2-sentence summary + 3 steps + mission alignment | Gemini |
| Personalization signals | Discipline, current module, years experience, tailoring query | Gemini |
| DB | PostgreSQL + pgvector on Mac Mini | Claude |
| Embedding / similarity | pgvector on PostgreSQL for article↔teacher matching | Claude |
| Frontend hosting | Express serves built React `dist/` (Vercel dropped) | Claude |

---

## Current Architecture (as deployed)

```
Browser
    │  HTTPS
    ▼
Cloudflare Quick Tunnel (trycloudflare.com — URL changes on restart)
    │
    ▼
Mac Mini — M4 Pro
 ├── Node.js / Express (port 3001)
 │    ├── serves built React frontend (frontend/dist/)
 │    ├── GET/POST /api/profile
 │    ├── GET /api/digest/me
 │    └── POST /api/digest/regenerate → spawns Python pipeline
 ├── Python Pipeline (venv)
 │    └── fetchers → filter → embed → LLM eval → DB write
 ├── LM Studio / MLX  ← NOT YET CONFIRMED RUNNING
 └── PostgreSQL 17 + pgvector
```

---

## Unified Database Schema

```sql
-- Faculty profiles (email is the natural PK, sourced from Cloudflare header)
CREATE TABLE faculty_profiles (
    email               VARCHAR(255) PRIMARY KEY,
    first_name          VARCHAR(100),
    last_name           VARCHAR(100),
    discipline          VARCHAR(100) NOT NULL,
    grade_band          VARCHAR(50),
    years_experience    INT NOT NULL,
    current_module      TEXT,
    tailoring_query     TEXT,
    discipline_key      VARCHAR(100),
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Source-agnostic article store
CREATE TABLE articles (
    id                  SERIAL PRIMARY KEY,
    source_id           VARCHAR(255) UNIQUE NOT NULL,
    source              VARCHAR(100),
    title               TEXT,
    full_text           TEXT,
    authors             TEXT,
    publication_date    DATE,
    url                 TEXT,
    embedding           vector(768),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Per-teacher evaluation & generated output
CREATE TABLE teacher_article_matches (
    id                  SERIAL PRIMARY KEY,
    teacher_email       VARCHAR(255) NOT NULL REFERENCES faculty_profiles(email) ON DELETE CASCADE,
    article_id          INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    decision            VARCHAR(20),
    summary             TEXT,
    action_steps        TEXT,
    mission_alignment   TEXT,
    similarity_score    FLOAT,
    status              VARCHAR(50) DEFAULT 'pending',
    date_evaluated      DATE DEFAULT CURRENT_DATE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (teacher_email, article_id)
);
```

---

## LLM Output Contract

```json
{
  "decision": "Yes",
  "summary": "Researchers found that retrieval practice outperforms re-reading for long-term retention in secondary students.",
  "action_steps": [
    "Open class with a 5-minute no-stakes quiz on yesterday's material before introducing new content.",
    "Replace one homework reading assignment this week with a written brain-dump exercise from memory.",
    "At unit end, have students create their own 10-question practice test and exchange with a peer."
  ],
  "mission_alignment": "This research directly supports Pace Academy's commitment to developing self-directed, intellectually curious learners by giving students tools to take ownership of their own retention."
}
```

| `years_experience` | Persona | Prompt emphasis |
|---|---|---|
| 0–3 | Novice | Classroom management, clear mechanics, simple execution |
| 4–9 | Developing | Differentiation, student engagement strategies |
| 10+ | Veteran | Advanced differentiation, avoiding curriculum fatigue, leadership |

---

## Task Assignments

### Phase 1 — Foundation

| # | Task | Owner | Status |
|---|---|---|---|
| 1.1 | PostgreSQL schema + pgvector setup | **Claude** | ✅ |
| 1.2 | `DatabaseManager` class | **Claude** | ✅ |
| 1.3 | SQLite shim for local dev | **Claude** | ⏭️ skipped — went straight to Postgres |
| 1.4 | `Config` class + `.env.example` | **Claude** | ✅ |
| 1.5 | Express API scaffold: profile + digest routes | **Gemini** | ✅ |
| 1.6 | CF header auth middleware | **Gemini** | ✅ |
| 1.7 | React app scaffold: Profile + Digest pages | **Gemini** | ✅ |
| 1.8 | Cloudflare Zero Trust policy for `@paceacademy.org` | **—** | ⏳ blocked — needs custom domain |
| 1.9 | Cloudflare Tunnel on Mac Mini → Express | **Claude** | ✅ (Quick Tunnel) |

---

### Phase 2 — Article Pipeline

| # | Task | Owner | Status |
|---|---|---|---|
| 2.1 | RSS fetcher (`feedparser`) | **Claude** | ✅ |
| 2.2 | `newspaper3k` full-text scraper | **Claude** | ✅ |
| 2.3 | Programmatic pre-filter | **Claude** | ✅ |
| 2.4 | Article embedder → pgvector | **Claude** | ✅ |
| 2.5 | Teacher tailoring-string embedder + cosine similarity shortlist | **Claude** | ✅ |

---

### Phase 3 — LLM Evaluation

| # | Task | Owner | Status |
|---|---|---|---|
| 3.1 | Master system prompt template | **Gemini** | ✅ |
| 3.2 | LLM call → parse + validate JSON | **Claude** | ✅ |
| 3.3 | Per-teacher article selection (top 3–5) | **Gemini** | ✅ |
| 3.4 | Healing pass for missing summaries | **Claude** | ✅ |
| 3.5 | `WorkflowManager.execute()` end-to-end orchestration | **Claude** | ✅ |

---

### Phase 4 — Digest Display & Polish

| # | Task | Owner | Status |
|---|---|---|---|
| 4.1 | Express `GET /api/digest/me` | **Gemini** | ✅ |
| 4.2 | React Digest Dashboard: article cards | **Gemini** | ✅ |
| 4.3 | "Regenerate Digest" button → pipeline trigger | **Gemini** | ✅ |
| 4.4 | HTML email formatter (optional) | **Claude** | ☐ |

---

### Phase 5 — Demo Hardening

| # | Task | Owner | Status |
|---|---|---|---|
| 5.1 | `start.sh` — single command start | **Claude** | ✅ |
| 5.2 | Seed 3 mock teacher personas | **Gemini** | ✅ |
| 5.3 | End-to-end smoke test | **Claude** | ✅ |
| 5.4 | `--dry-run` flag for pipeline | **Claude** | ✅ |

---

### Phase 6 — Remote Deployment (Mac Mini) ← CURRENT PHASE

| # | Task | Status | Notes |
|---|---|---|---|
| 6.1 | SSH access to Mac Mini via Tailscale | ✅ | `compsci@100.110.5.126` |
| 6.2 | Repo cloned to Mac Mini | ✅ | `~/Documents/Github/pace-ai-edu` |
| 6.3 | Python venv + all dependencies installed | ✅ | `python3.13 -m venv venv` |
| 6.4 | Node + npm installed (Homebrew) | ✅ | |
| 6.5 | PostgreSQL 17 + pgvector installed and running | ✅ | `brew services start postgresql@17` |
| 6.6 | Database schema applied + mock data seeded | ✅ | |
| 6.7 | Frontend built + served by Express | ✅ | Express serves `frontend/dist/` |
| 6.8 | Cloudflare Quick Tunnel running, app accessible remotely | ✅ | URL rotates on restart |
| 6.9 | Keep process alive after SSH disconnect | ⏳ **TODO** | Install tmux: `brew install tmux` |
| 6.10 | Fix PostgreSQL auto-start in `start.sh` (PGDATA warning) | ⏳ **TODO** | Set `PGDATA` in `.env` or use `brew services` check |
| 6.11 | LM Studio installed + models loaded on Mac Mini | ⏳ **TODO** | Needed for pipeline to run |
| 6.12 | Run pipeline end-to-end to populate `teacher_article_matches` | ⏳ **TODO** | Blocked on 6.11 |
| 6.13 | Confirm "Regenerate" button triggers venv Python (not system python3) | ⏳ **TODO** | `digest.js` spawns `python3` — needs to use venv |
| 6.14 | Permanent URL + Zero Trust email gate | ⏳ **TODO** | Requires purchasing a domain (~$1-2/yr) |

---

### Gemini Tasks — Discipline-Key Refactor (completed)

| # | Task | Status |
|---|---|---|
| G1 | Add `discipline_key` to `POST /profile` | ✅ |
| G2 | Add `discipline_key` dropdown to Profile Setup page | ✅ |
| G3 | Return `discipline_key` in `GET /profile` response | ✅ |

---

## Immediate Next Steps (priority order)

1. `brew install tmux` on Mac Mini → keep `start.sh` alive after SSH disconnect
2. Install LM Studio on Mac Mini + load embedding + chat models
3. Run pipeline: `python3 -m pipeline.workflow` (from within venv)
4. Fix `digest.js` regenerate endpoint to use venv python
5. Buy a domain → set up named Cloudflare Tunnel + Zero Trust policy

---

## File Structure (current)

```
pace-ai-edu/
├── .env.example
├── .env                            # ← NOT in git (copy from .env.example)
├── start.sh                        # starts Postgres, Express, Cloudflare tunnel
├── setup_mac_mini.sh               # one-time setup script
├── CLOUDFLARE_SETUP.md             # tunnel setup instructions
│
├── backend/
│   ├── server.js                   # Express + static frontend serving
│   ├── middleware/auth.js           # CF header auth + DEV_EMAIL fallback
│   └── routes/
│       ├── profile.js              # GET/POST /api/profile
│       └── digest.js               # GET /api/digest/me, POST /api/digest/regenerate
│
├── frontend/
│   ├── dist/                       # built output (served by Express)
│   ├── src/
│   │   ├── pages/Profile.jsx
│   │   └── pages/Digest.jsx
│   └── vite.config.js
│
├── pipeline/
│   ├── config.py
│   ├── database.py
│   ├── fetchers/
│   │   ├── rss_fetcher.py
│   │   ├── eric_fetcher.py
│   │   └── scraper.py
│   ├── article_filter.py
│   ├── embedder.py
│   ├── evaluator.py
│   ├── personalizer.py
│   └── workflow.py
│
├── schema.sql
├── seed_mock_data.sql
├── seed_teachers.py
├── requirements.txt
└── venv/                           # ← NOT in git
```
