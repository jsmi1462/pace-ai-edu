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
| Article sources (v1) | RSS scraping — Cult of Pedagogy, Edutopia, ASCD | Gemini |
| Delivery mechanism | React dashboard + optional email | Gemini |
| Auth | Cloudflare Zero Trust → `@paceacademy.edu` only | Gemini |
| Compute | M4 Mac Mini (48GB) on-premises via Tailscale + Cloudflare Tunnel | Gemini |
| Output format | 2-sentence summary + 3 steps + mission alignment | Gemini |
| Personalization signals | Discipline, current module, years experience, tailoring query | Gemini |
| DB for v1 | SQLite → PostgreSQL migration path | Gemini |
| Embedding / similarity | pgvector on PostgreSQL for article↔teacher matching | Claude |

---

## Full Stack

```
Browser (Vercel)
    │  HTTPS
    ▼
Cloudflare Zero Trust
    │  strips anon, injects Cf-Access-Authenticated-User-Email header
    ▼
Cloudflare Tunnel (cloudflared)
    │  no inbound ports
    ▼
Mac Mini (local)
 ├── Node.js / Express API        ← REST endpoints, reads CF header = auth
 ├── Python Pipeline              ← fetching, filtering, LLM eval, DB writes
 ├── LM Studio / MLX              ← local LLM inference (zero-cost)
 └── PostgreSQL + pgvector        ← articles, faculty profiles, matches
```

---

## Unified Database Schema

```sql
-- Faculty profiles (email is the natural PK, sourced from Cloudflare header)
CREATE TABLE faculty_profiles (
    email               VARCHAR(255) PRIMARY KEY,
    first_name          VARCHAR(100),
    last_name           VARCHAR(100),
    discipline          VARCHAR(100) NOT NULL,       -- e.g. "AP Chemistry", "7th Grade English"
    grade_band          VARCHAR(50),                 -- e.g. "K-5", "6-8", "9-12"
    years_experience    INT NOT NULL,                -- drives prompt persona selection
    current_module      TEXT,                        -- unit/topic being taught right now
    tailoring_query     TEXT,                        -- free-form improvement goals
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Source-agnostic article store
CREATE TABLE articles (
    id                  SERIAL PRIMARY KEY,
    source_id           VARCHAR(255) UNIQUE NOT NULL, -- URL hash or ERIC accession #
    source              VARCHAR(100),                 -- 'Edutopia', 'ASCD', etc.
    title               TEXT,
    full_text           TEXT,                         -- scraped body (newspaper3k)
    authors             TEXT,
    publication_date    DATE,
    url                 TEXT,
    embedding           vector(768),                  -- pgvector
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Per-teacher evaluation & generated output
CREATE TABLE teacher_article_matches (
    id                  SERIAL PRIMARY KEY,
    teacher_email       VARCHAR(255) NOT NULL REFERENCES faculty_profiles(email) ON DELETE CASCADE,
    article_id          INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    decision            VARCHAR(20),                  -- 'Yes' | 'No' | 'Error'
    summary             TEXT,                         -- 2-sentence summary
    action_steps        TEXT,                         -- 3 actionable steps (JSON array or numbered text)
    mission_alignment   TEXT,                         -- 1-sentence Pace mission tie-in
    similarity_score    FLOAT,
    status              VARCHAR(50) DEFAULT 'pending',
    date_evaluated      DATE DEFAULT CURRENT_DATE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (teacher_email, article_id)
);
```

---

## LLM Output Contract

Every article evaluation call returns a single JSON object:

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

**Prompt persona logic (Gemini owns this):**

| `years_experience` | Persona | Prompt emphasis |
|---|---|---|
| 0–3 | Novice | Classroom management, clear mechanics, simple execution |
| 4–9 | Developing | Differentiation, student engagement strategies |
| 10+ | Veteran | Advanced differentiation, avoiding curriculum fatigue, leadership |

---

## Task Assignments

### Phase 1 — Foundation (Day 1 AM)

| # | Task | Owner | Status |
|---|---|---|---|
| 1.1 | PostgreSQL schema + pgvector setup | **Claude** | ✅ |
| 1.2 | `DatabaseManager` class (upsert_article, upsert_match, fetch_for_teacher) | **Claude** | ✅ |
| 1.3 | SQLite shim for local dev without Postgres | **Claude** | ☐ |
| 1.4 | `Config` class + `.env.example` (LM Studio URL, DB URL, etc.) | **Claude** | ✅ |
| 1.5 | Express API scaffold: `GET /profile`, `POST /profile`, `GET /digest/:email` | **Gemini** | ✅ |
| 1.6 | CF header auth middleware (`req.user = req.headers['cf-access-authenticated-user-email']`) | **Gemini** | ✅ |
| 1.7 | React app scaffold: Profile Setup page + Digest Dashboard page | **Gemini** | ✅ |
| 1.8 | Vercel deploy + Cloudflare Zero Trust policy for `@paceacademy.edu` | **Gemini** | ☐ |
| 1.9 | Cloudflare Tunnel on Mac Mini → Express API | **Gemini** | ☐ |

---

### Phase 2 — Article Pipeline (Day 1 PM)

| # | Task | Owner | Status |
|---|---|---|---|
| 2.1 | RSS fetcher (`feedparser`) for Edutopia, Cult of Pedagogy, ASCD | **Claude** | ✅ |
| 2.2 | `newspaper3k` full-text scraper (strip boilerplate, extract core text) | **Claude** | ✅ |
| 2.3 | Programmatic pre-filter (exclude op-eds, listicles, press releases) | **Claude** | ✅ |
| 2.4 | Article embedder (call local LM Studio embedding endpoint → store in pgvector) | **Claude** | ✅ |
| 2.5 | Teacher tailoring-string embedder + cosine similarity shortlist | **Claude** | ✅ |

---

### Phase 3 — LLM Evaluation (Day 1 PM → Day 2 AM)

| # | Task | Owner | Status |
|---|---|---|---|
| 3.1 | Master system prompt template (discipline + module + experience persona + mission) | **Gemini** | ✅ |
| 3.2 | LLM call → parse + validate JSON output contract (above) | **Claude** | ✅ |
| 3.3 | Per-teacher article selection: cull to top 3–5 by relevance score | **Gemini** | ✅ |
| 3.4 | Healing pass: re-generate missing summaries/steps for existing DB records | **Claude** | ✅ |
| 3.5 | `WorkflowManager.execute()` — orchestrates 2.x → 3.x pipeline end-to-end | **Claude** | ✅ |

---

### Phase 4 — Digest Display & Polish (Day 2 AM)

| # | Task | Owner | Status |
|---|---|---|---|
| 4.1 | Express endpoint: `GET /digest/:email` returns matched articles with full output | **Gemini** | ✅ |
| 4.2 | React Digest Dashboard: render article cards (title, summary, 3 steps, mission line) | **Gemini** | ✅ |
| 4.3 | "Regenerate Digest" button → POST to pipeline trigger endpoint | **Gemini** | ✅ |
| 4.4 | HTML email formatter (optional — if time allows before demo) | **Claude** | ☐ |

---

### Phase 5 — Demo Hardening (Day 2 PM)

| # | Task | Owner | Status |
|---|---|---|---|
| 5.1 | `start.sh` — single command starts Postgres, Express, Python pipeline, LM Studio | **Gemini** | ✅ |
| 5.2 | Seed 3 mock teacher personas for demo (novice math, mid-career English, veteran history) | **Gemini** | ✅ |
| 5.3 | End-to-end smoke test: pipeline runs, DB populates, dashboard renders 3–5 articles | **Claude** | ✅ |
| 5.4 | `--dry-run` flag: run pipeline without writing to DB or triggering LLM (for CI) | **Claude** | ✅ |

---

## File Structure (target)

```
pace-ai-edu/
├── .env.example
├── start.sh                        # demo launcher
│
├── backend/                        # Node.js / Express
│   ├── server.js
│   ├── middleware/auth.js           # Cloudflare header parser
│   └── routes/
│       ├── profile.js
│       └── digest.js
│
├── frontend/                       # React (Vercel)
│   ├── src/
│   │   ├── pages/Profile.jsx
│   │   └── pages/Digest.jsx
│   └── ...
│
├── pipeline/                       # Python
│   ├── config.py
│   ├── database.py                 # DatabaseManager
│   ├── fetchers/
│   │   ├── rss_fetcher.py
│   │   └── scraper.py              # newspaper3k
│   ├── article_filter.py
│   ├── embedder.py
│   ├── evaluator.py                # LLM calls + JSON parsing
│   ├── personalizer.py             # cosine similarity shortlist
│   └── workflow.py                 # WorkflowManager
│
├── headless_app.py                 # reference — medical pipeline
├── GEMINI.md                       # Gemini's architecture notes
├── projectmap.md                   # user story
└── assignments.md                  # this file
```

---

---

## Gemini — New Tasks (Discipline-Key Refactor)

These are blocking for a complete product. Claude has shipped the Python side.

| # | Task | Detail |
|---|---|---|
| G1 | Add `discipline_key` to Express `POST /profile` | Save to `faculty_profiles.discipline_key` column (already exists in DB) |
| G2 | Add `discipline_key` dropdown to React Profile Setup page | Options must come from the list below. Label the field "Teaching Discipline". |
| G3 | Return `discipline_key` in Express `GET /profile` response | Frontend needs it to show the current selection |

**Discipline key options for the dropdown** (value → display label):

```
ls_homeroom       → Lower School: Homeroom / Lead Teacher
ls_math           → Lower School: Math
ls_science        → Lower School: Science
ls_steam          → Lower School: STEAM
ls_world_language → Lower School: World Language
ls_arts           → Lower School: Arts & Music
ls_pe             → Lower School: Physical Education
ls_library        → Lower School: Library
ls_learning_support → Lower School: Learning Support
ms_english        → Middle School: English
ms_math           → Middle School: Math
ms_science        → Middle School: Science
ms_history        → Middle School: History & Social Studies
ms_world_language → Middle School: World Language
ms_pe             → Middle School: Physical Education
ms_steam          → Middle School: STEAM
ms_arts           → Middle School: Arts & Music
ms_debate         → Middle School: Debate
us_english        → Upper School: English
us_math           → Upper School: Math
us_science        → Upper School: Science
us_history        → Upper School: History & Social Studies
us_world_language → Upper School: World Language
us_cs             → Upper School: Computer Science
us_arts           → Upper School: Arts & Performing Arts
us_social_science → Upper School: Economics / Psychology / Social Sciences
us_learning_support → Upper School: Learning Support
global_leadership → Cross-Division: Global Leadership
counseling        → Cross-Division: Counseling & SEL
```

---

## Interface Contract Between Claude & Gemini

The Python pipeline writes to PostgreSQL. The Express API reads from it. The handoff:

- Pipeline writes `teacher_article_matches` rows with `status = 'pending'`
- Express `GET /digest/:email` queries `teacher_article_matches JOIN articles WHERE teacher_email = ? AND decision = 'Yes' AND status = 'pending'`
- React renders the returned JSON

**Nothing else crosses the boundary.** Python never calls Express. Express never calls Python directly (pipeline is triggered separately, either by cron or the "Regenerate" button hitting a pipeline trigger endpoint).
