import logging
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor, execute_values
from .config import CONFIG


def get_db_connection(database_url: str):
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except psycopg2.OperationalError as e:
        logging.critical(f"Cannot connect to database: {e}")
        raise


class DatabaseManager:
    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def setup_pgvector(self) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(
                    f"ALTER TABLE articles ADD COLUMN IF NOT EXISTS "
                    f"embedding vector({CONFIG.EMBEDDING_DIMENSIONS});"
                )
            self.conn.commit()
            logging.info(f"pgvector ready (dim={CONFIG.EMBEDDING_DIMENSIONS}).")
            return True
        except Exception as e:
            logging.warning(f"pgvector setup failed: {e}")
            self.conn.rollback()
            return False

    def create_tables(self):
        commands = [
            """
            CREATE TABLE IF NOT EXISTS faculty_profiles (
                email               VARCHAR(255) PRIMARY KEY,
                first_name          VARCHAR(100),
                last_name           VARCHAR(100),
                discipline          VARCHAR(100) NOT NULL,
                grade_band          VARCHAR(50),
                years_experience    INT NOT NULL DEFAULT 0,
                current_module      TEXT,
                tailoring_query     TEXT,
                discipline_key      TEXT,
                is_active           BOOLEAN DEFAULT TRUE,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Migrate existing faculty_profiles tables that predate discipline_key
            "ALTER TABLE faculty_profiles ADD COLUMN IF NOT EXISTS discipline_key TEXT",
            """
            CREATE TABLE IF NOT EXISTS articles (
                id                  SERIAL PRIMARY KEY,
                source_id           VARCHAR(255) UNIQUE NOT NULL,
                source              VARCHAR(100),
                title               TEXT,
                full_text           TEXT,
                authors             TEXT,
                publication_date    DATE,
                url                 TEXT,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS article_disciplines (
                article_id          INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                discipline_key      TEXT NOT NULL,
                PRIMARY KEY (article_id, discipline_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_article_disciplines_key ON article_disciplines(discipline_key)",
            """
            CREATE TABLE IF NOT EXISTS teacher_article_matches (
                id                  SERIAL PRIMARY KEY,
                teacher_email       VARCHAR(255) NOT NULL
                                        REFERENCES faculty_profiles(email) ON DELETE CASCADE,
                article_id          INTEGER NOT NULL
                                        REFERENCES articles(id) ON DELETE CASCADE,
                decision            VARCHAR(20),
                summary             TEXT,
                action_steps        TEXT,
                mission_alignment   TEXT,
                similarity_score    FLOAT,
                status              VARCHAR(50) DEFAULT 'pending',
                date_evaluated      DATE DEFAULT CURRENT_DATE,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (teacher_email, article_id)
            )
            """,
        ]
        try:
            with self.conn.cursor() as cur:
                for cmd in commands:
                    cur.execute(cmd)
            self.conn.commit()
            logging.info("Database tables ensured.")
        except Exception as e:
            logging.error(f"Error creating tables: {e}")
            self.conn.rollback()
            raise

    def backfill_general_tags(self) -> int:
        """
        Tags all existing articles that have no discipline tag yet as 'general'
        so they're reachable by vector search until the discipline-specific
        ERIC fetch repopulates the DB.
        """
        q = """
            INSERT INTO article_disciplines (article_id, discipline_key)
            SELECT a.id, 'general'
            FROM articles a
            WHERE NOT EXISTS (
                SELECT 1 FROM article_disciplines ad WHERE ad.article_id = a.id
            )
            ON CONFLICT DO NOTHING;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(q)
                count = cur.rowcount
            self.conn.commit()
            if count:
                logging.info(f"Backfilled {count} legacy articles with 'general' discipline tag.")
            return count
        except Exception as e:
            logging.warning(f"backfill_general_tags failed: {e}")
            self.conn.rollback()
            return 0

    # ------------------------------------------------------------------
    # Faculty profiles
    # ------------------------------------------------------------------

    def upsert_teacher(self, profile: dict) -> None:
        q = """
            INSERT INTO faculty_profiles
                (email, first_name, last_name, discipline, grade_band,
                 years_experience, current_module, tailoring_query, discipline_key)
            VALUES
                (%(email)s, %(first_name)s, %(last_name)s, %(discipline)s,
                 %(grade_band)s, %(years_experience)s, %(current_module)s,
                 %(tailoring_query)s, %(discipline_key)s)
            ON CONFLICT (email) DO UPDATE SET
                first_name       = EXCLUDED.first_name,
                last_name        = EXCLUDED.last_name,
                discipline       = EXCLUDED.discipline,
                grade_band       = EXCLUDED.grade_band,
                years_experience = EXCLUDED.years_experience,
                current_module   = EXCLUDED.current_module,
                tailoring_query  = EXCLUDED.tailoring_query,
                discipline_key   = EXCLUDED.discipline_key,
                updated_at       = CURRENT_TIMESTAMP;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(q, {
                    "email":            profile.get("email"),
                    "first_name":       profile.get("first_name", ""),
                    "last_name":        profile.get("last_name", ""),
                    "discipline":       profile.get("discipline", "General Education"),
                    "grade_band":       profile.get("grade_band", ""),
                    "years_experience": int(profile.get("years_experience", 0)),
                    "current_module":   profile.get("current_module", ""),
                    "tailoring_query":  profile.get("tailoring_query", ""),
                    "discipline_key":   profile.get("discipline_key"),
                })
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error upserting teacher {profile.get('email')}: {e}")
            self.conn.rollback()

    def fetch_active_teachers(self, email: str = None) -> list[dict]:
        q = "SELECT * FROM faculty_profiles WHERE is_active = TRUE"
        params = []
        if email:
            q += " AND email = %s"
            params.append(email)
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(q, params)
            return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Articles
    # ------------------------------------------------------------------

    def upsert_article(self, article: dict) -> int | None:
        q = """
            INSERT INTO articles
                (source_id, source, title, full_text, authors, publication_date, url)
            VALUES
                (%(source_id)s, %(source)s, %(title)s, %(full_text)s,
                 %(authors)s, %(publication_date)s, %(url)s)
            ON CONFLICT (source_id) DO UPDATE SET
                title            = EXCLUDED.title,
                full_text        = EXCLUDED.full_text,
                publication_date = EXCLUDED.publication_date
            RETURNING id;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(q, {
                    "source_id":        article["source_id"],
                    "source":           article.get("source", ""),
                    "title":            article.get("title", ""),
                    "full_text":        article.get("full_text", ""),
                    "authors":          article.get("authors", ""),
                    "publication_date": article.get("publication_date"),
                    "url":              article.get("url", ""),
                })
                row = cur.fetchone()
            self.conn.commit()
            return row[0] if row else None
        except Exception as e:
            logging.error(f"Error upserting article {article.get('source_id')}: {e}")
            self.conn.rollback()
            return None

    def upsert_article_embedding(self, article_id: int, embedding: list[float]) -> None:
        if not article_id or not embedding:
            return
        vec = '[' + ','.join(f'{x:.8f}' for x in embedding) + ']'
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE articles SET embedding = %s::vector WHERE id = %s",
                    (vec, article_id),
                )
            self.conn.commit()
        except Exception as e:
            logging.warning(f"Failed to store embedding for article {article_id}: {e}")
            self.conn.rollback()

    def tag_article_discipline(self, article_id: int, discipline_key: str) -> None:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO article_disciplines (article_id, discipline_key) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (article_id, discipline_key),
                )
            self.conn.commit()
        except Exception as e:
            logging.warning(f"tag_article_discipline failed ({article_id}, {discipline_key}): {e}")
            self.conn.rollback()

    def search_articles_by_vector(
        self,
        discipline_key: str | None,
        query_embedding: list[float],
        limit: int = 50,
    ) -> list[dict]:
        """
        Returns the top `limit` articles ordered by cosine distance to query_embedding,
        filtered to the teacher's discipline pool plus 'general' (RSS articles).
        Falls back to searching all tagged articles if discipline_key is None.
        """
        vec = '[' + ','.join(f'{x:.8f}' for x in query_embedding) + ']'

        if discipline_key:
            discipline_filter = "ad.discipline_key IN %s"
            discipline_params = ((discipline_key, 'general'),)
        else:
            discipline_filter = "TRUE"
            discipline_params = ()

        q = f"""
            SELECT DISTINCT ON (a.id)
                a.id, a.source_id, a.source, a.title, a.full_text,
                a.authors, a.publication_date, a.url,
                (a.embedding <=> %s::vector) AS distance
            FROM articles a
            JOIN article_disciplines ad ON a.id = ad.article_id
            WHERE {discipline_filter}
              AND a.embedding IS NOT NULL
            ORDER BY a.id, distance ASC
            LIMIT %s;
        """
        try:
            with self.conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(q, (vec,) + discipline_params + (limit,))
                rows = cur.fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d['_db_id'] = d['id']
                d['_distance'] = d.pop('distance', 1.0)
                results.append(d)
            # Re-sort by distance ascending (DISTINCT ON ordering may vary)
            results.sort(key=lambda r: r['_distance'])
            return results
        except Exception as e:
            logging.warning(f"Vector search failed: {e}")
            self.conn.rollback()
            return []

    def count_articles(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM articles;")
            return cur.fetchone()[0]

    def get_already_seen_source_ids(self, source_ids: list[str]) -> set[str]:
        if not source_ids:
            return set()
        with self.conn.cursor() as cur:
            cur.execute("SELECT source_id FROM articles WHERE source_id = ANY(%s)", (source_ids,))
            return {row[0] for row in cur.fetchall()}

    def search_articles_by_keywords(self, keywords: list[str], limit: int = 50) -> list[dict]:
        """
        Full-text search over articles using PostgreSQL tsvector.
        Joins all keywords into a single tsquery (OR semantics) and ranks by relevance.
        Falls back to empty list if no keywords provided.
        """
        if not keywords:
            return []

        # Build a tsquery: "keyword1 | keyword2 | keyword3"
        tsquery = " | ".join(
            " & ".join(word for word in kw.split())
            for kw in keywords if kw.strip()
        )
        if not tsquery:
            return []

        q = """
            SELECT
                id, source_id, source, title, full_text,
                authors, publication_date, url,
                ts_rank(
                    to_tsvector('english', COALESCE(title,'') || ' ' || COALESCE(full_text,'')),
                    to_tsquery('english', %s)
                ) AS rank
            FROM articles
            WHERE to_tsvector('english', COALESCE(title,'') || ' ' || COALESCE(full_text,''))
                  @@ to_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s;
        """
        try:
            with self.conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(q, (tsquery, tsquery, limit))
                rows = cur.fetchall()
            # Map DB 'id' to '_db_id' so workflow can use it uniformly
            results = []
            for row in rows:
                d = dict(row)
                d['_db_id'] = d['id']
                results.append(d)
            return results
        except Exception as e:
            logging.warning(f"Full-text search failed (keywords={keywords}): {e}")
            self.conn.rollback()
            return []

    # ------------------------------------------------------------------
    # Teacher ↔ Article matches
    # ------------------------------------------------------------------

    def upsert_match(self, teacher_email: str, article_id: int, data: dict) -> int | None:
        q = """
            INSERT INTO teacher_article_matches
                (teacher_email, article_id, decision, summary, action_steps,
                 mission_alignment, similarity_score, status)
            VALUES
                (%(teacher_email)s, %(article_id)s, %(decision)s, %(summary)s,
                 %(action_steps)s, %(mission_alignment)s, %(similarity_score)s, 'pending')
            ON CONFLICT (teacher_email, article_id) DO UPDATE SET
                decision          = EXCLUDED.decision,
                summary           = EXCLUDED.summary,
                action_steps      = EXCLUDED.action_steps,
                mission_alignment = EXCLUDED.mission_alignment,
                similarity_score  = EXCLUDED.similarity_score,
                status            = 'pending',
                date_evaluated    = CURRENT_DATE
            WHERE teacher_article_matches.status NOT LIKE 'sent%%'
            RETURNING id;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(q, {
                    "teacher_email":    teacher_email,
                    "article_id":       article_id,
                    "decision":         data.get("decision"),
                    "summary":          data.get("summary"),
                    "action_steps":     data.get("action_steps"),
                    "mission_alignment": data.get("mission_alignment"),
                    "similarity_score": data.get("similarity_score"),
                })
                row = cur.fetchone()
            self.conn.commit()
            return row[0] if row else None
        except Exception as e:
            logging.error(f"Error upserting match teacher={teacher_email} article={article_id}: {e}")
            self.conn.rollback()
            return None

    def fetch_digest_for_teacher(self, teacher_email: str) -> list[dict]:
        """Returns the current pending Yes-articles for a teacher — used by Express API."""
        q = """
            SELECT
                a.title, a.url, a.source, a.authors, a.publication_date,
                m.summary, m.action_steps, m.mission_alignment,
                m.similarity_score, m.date_evaluated
            FROM teacher_article_matches m
            JOIN articles a ON m.article_id = a.id
            WHERE m.teacher_email = %s
              AND m.decision = 'Yes'
              AND m.status = 'pending'
            ORDER BY m.similarity_score DESC NULLS LAST, m.date_evaluated DESC;
        """
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(q, (teacher_email,))
            return [dict(row) for row in cur.fetchall()]

    def fetch_yes_embeddings_for_teacher(self, teacher_email: str) -> list[list[float]]:
        """Returns embeddings of all Yes-articles for a teacher (for corpus-building)."""
        q = """
            SELECT a.embedding::text
            FROM teacher_article_matches m
            JOIN articles a ON m.article_id = a.id
            WHERE m.teacher_email = %s AND m.decision = 'Yes' AND a.embedding IS NOT NULL;
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(q, (teacher_email,))
                rows = cur.fetchall()
            return [
                [float(x) for x in row[0].strip('[]').split(',')]
                for row in rows if row[0]
            ]
        except Exception as e:
            logging.warning(f"Failed to fetch Yes embeddings for {teacher_email}: {e}")
            return []

    def mark_digest_sent(self, teacher_email: str) -> None:
        q = """
            UPDATE teacher_article_matches
            SET status = 'sent', updated_at = CURRENT_TIMESTAMP
            WHERE teacher_email = %s AND decision = 'Yes' AND status = 'pending';
        """
        with self.conn.cursor() as cur:
            cur.execute(q, (teacher_email,))
        self.conn.commit()
