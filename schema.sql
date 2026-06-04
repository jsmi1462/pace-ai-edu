CREATE EXTENSION IF NOT EXISTS vector;

-- Faculty profiles (email is the natural PK, sourced from Cloudflare header)
CREATE TABLE IF NOT EXISTS faculty_profiles (
    email               VARCHAR(255) PRIMARY KEY,
    first_name          VARCHAR(100),
    last_name           VARCHAR(100),
    discipline          VARCHAR(100) NOT NULL,       -- e.g. "AP Chemistry", "7th Grade English"
    grade_band          VARCHAR(50),                 -- e.g. "K-5", "6-8", "9-12"
    years_experience    INT NOT NULL,                -- drives prompt persona selection
    current_module      TEXT,                        -- unit/topic being taught right now
    tailoring_query     TEXT,                        -- free-form improvement goals
    discipline_key      TEXT,                        -- maps to DISCIPLINE_ERIC_QUERIES (e.g. "ms_math")
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Source-agnostic article store
CREATE TABLE IF NOT EXISTS articles (
    id                  SERIAL PRIMARY KEY,
    source_id           VARCHAR(255) UNIQUE NOT NULL, -- URL hash or ERIC accession #
    source              VARCHAR(100),                 -- 'Cult of Pedagogy', 'ERIC', etc.
    title               TEXT,
    full_text           TEXT,                         -- scraped body or ERIC abstract
    authors             TEXT,
    publication_date    DATE,
    url                 TEXT,
    embedding           vector(768),                  -- pgvector; set at ingest time
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Discipline tags for articles (many-to-many)
-- RSS articles → 'general'; ERIC articles → their discipline_key
CREATE TABLE IF NOT EXISTS article_disciplines (
    article_id          INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    discipline_key      TEXT NOT NULL,
    PRIMARY KEY (article_id, discipline_key)
);
CREATE INDEX IF NOT EXISTS idx_article_disciplines_key ON article_disciplines(discipline_key);

-- Per-teacher evaluation & generated output
CREATE TABLE IF NOT EXISTS teacher_article_matches (
    id                  SERIAL PRIMARY KEY,
    teacher_email       VARCHAR(255) NOT NULL REFERENCES faculty_profiles(email) ON DELETE CASCADE,
    article_id          INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    decision            VARCHAR(20),                  -- 'Yes' | 'No' | 'Error'
    summary             TEXT,                         -- 2-sentence summary
    action_steps        TEXT,                         -- 3 actionable steps (JSON array)
    mission_alignment   TEXT,                         -- 1-sentence Pace mission tie-in
    similarity_score    FLOAT,                        -- 1 - cosine_distance (higher = more similar)
    status              VARCHAR(50) DEFAULT 'pending',
    date_evaluated      DATE DEFAULT CURRENT_DATE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_rating         VARCHAR(12) CHECK (user_rating IN ('awesome', 'good', 'bad', 'irrelevant')),
    UNIQUE (teacher_email, article_id)
);
