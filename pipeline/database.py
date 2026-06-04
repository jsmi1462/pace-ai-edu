import logging
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor, execute_values
from .config import CONFIG


def get_db_connection(database_url: str):
    try:
        conn = psycopg2.connect(database_url)
        # Async WAL flush: commits return immediately without waiting for disk.
        # Reads are completely unaffected (MVCC). Worst-case loss on a hard crash
        # is ~1 commit — the end-of-run cleanup catches any gap.
        with conn.cursor() as cur:
            cur.execute("SET synchronous_commit = off")
        conn.commit()
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

    def batch_upsert_articles(self, articles: list[dict], chunk_size: int = 50) -> dict[str, int]:
        """
        Batch-upsert articles in chunks. Returns {source_id: db_id} for every row
        successfully written. Each chunk is one commit — far less WAL pressure than
        one commit per row.
        """
        id_map: dict[str, int] = {}
        for i in range(0, len(articles), chunk_size):
            chunk = articles[i:i + chunk_size]
            records = [(
                a['source_id'], a.get('source', ''), a.get('title', ''),
                a.get('full_text', ''), a.get('authors', ''),
                a.get('publication_date'), a.get('url', ''),
            ) for a in chunk]
            try:
                with self.conn.cursor() as cur:
                    rows = execute_values(cur, """
                        INSERT INTO articles
                            (source_id, source, title, full_text, authors, publication_date, url)
                        VALUES %s
                        ON CONFLICT (source_id) DO UPDATE SET
                            title            = EXCLUDED.title,
                            full_text        = EXCLUDED.full_text,
                            publication_date = EXCLUDED.publication_date
                        RETURNING id, source_id
                    """, records, fetch=True)
                    for row in rows:
                        id_map[row[1]] = row[0]
                self.conn.commit()
                logging.info(f"batch_upsert_articles: chunk {i // chunk_size + 1} → {len(rows)} rows")
            except Exception as e:
                logging.error(f"batch_upsert_articles chunk {i // chunk_size + 1} failed: {e}")
                self.conn.rollback()
        return id_map

    def batch_update_embeddings(self, id_emb_pairs: list[tuple[int, list[float]]], chunk_size: int = 50) -> None:
        """Batch-update the embedding column. Chunks keep transactions short."""
        for i in range(0, len(id_emb_pairs), chunk_size):
            chunk = id_emb_pairs[i:i + chunk_size]
            records = [
                ('[' + ','.join(f'{x:.8f}' for x in emb) + ']', article_id)
                for article_id, emb in chunk
            ]
            try:
                with self.conn.cursor() as cur:
                    execute_values(cur, """
                        UPDATE articles SET embedding = data.emb::vector
                        FROM (VALUES %s) AS data(emb, id)
                        WHERE articles.id = data.id::int
                    """, records)
                self.conn.commit()
            except Exception as e:
                logging.error(f"batch_update_embeddings chunk {i // chunk_size + 1} failed: {e}")
                self.conn.rollback()

    def batch_tag_disciplines(self, id_dk_pairs: list[tuple[int, str]], chunk_size: int = 200) -> None:
        """Batch-insert article discipline tags."""
        for i in range(0, len(id_dk_pairs), chunk_size):
            chunk = id_dk_pairs[i:i + chunk_size]
            try:
                with self.conn.cursor() as cur:
                    execute_values(cur, """
                        INSERT INTO article_disciplines (article_id, discipline_key)
                        VALUES %s ON CONFLICT DO NOTHING
                    """, chunk)
                self.conn.commit()
            except Exception as e:
                logging.error(f"batch_tag_disciplines chunk {i // chunk_size + 1} failed: {e}")
                self.conn.rollback()

    def get_articles_missing_embeddings(self, limit: int = 2000) -> list[dict]:
        """Returns articles that were written but never embedded — crash recovery."""
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                "SELECT id, title, full_text FROM articles WHERE embedding IS NULL LIMIT %s",
                (limit,)
            )
            return [dict(row) for row in cur.fetchall()]

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
            exists_clause = """EXISTS (
                SELECT 1 FROM article_disciplines ad
                WHERE ad.article_id = a.id AND ad.discipline_key IN %s
            )"""
            exists_params = ((discipline_key, 'general'),)
        else:
            exists_clause = """EXISTS (
                SELECT 1 FROM article_disciplines ad WHERE ad.article_id = a.id
            )"""
            exists_params = ()

        q = f"""
            SELECT
                a.id, a.source_id, a.source, a.title, a.full_text,
                a.authors, a.publication_date, a.url,
                (a.embedding <=> %s::vector) AS distance
            FROM articles a
            WHERE {exists_clause}
              AND a.embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT %s;
        """
        try:
            with self.conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(q, (vec,) + exists_params + (limit,))
                rows = cur.fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d['_db_id'] = d['id']
                d['_distance'] = d.pop('distance', 1.0)
                results.append(d)
            return results
        except Exception as e:
            logging.warning(f"Vector search failed: {e}")
            self.conn.rollback()
            return []

    def count_articles(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM articles;")
            return cur.fetchone()[0]

    def get_evaluated_article_ids(self, teacher_email: str) -> set[int]:
        """Returns article IDs already evaluated (Yes or No) for this teacher — skip re-evaluation.
        Error decisions are excluded so failed evaluations are retried on the next run."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT article_id FROM teacher_article_matches
                   WHERE teacher_email = %s AND decision IN ('Yes', 'No')""",
                (teacher_email,)
            )
            return {row[0] for row in cur.fetchall()}

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
