"""
WorkflowManager: orchestrates the full pipeline for one run.

Usage:
    python -m pipeline.workflow [--teacher email@paceacademy.org] [--dry-run]
"""

import json as _json
import logging
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .config import CONFIG

# Asymmetric weights: awesome pulls hard, irrelevant repels hard
_RATING_WEIGHTS = {'awesome': 1.0, 'good': 0.35, 'bad': -0.3, 'irrelevant': -1.0}

def _apply_rocchio_nudge(
    query_emb: list[float],
    rated: list[tuple[list[float], str]],
    alpha: float,
) -> list[float]:
    """Shifts query_emb toward awesome/good articles and away from bad/irrelevant ones."""
    if not rated:
        return query_emb
    dim = len(query_emb)
    nudge = [0.0] * dim
    for emb, rating in rated:
        w = _RATING_WEIGHTS.get(rating, 0.0)
        if w:
            for i, v in enumerate(emb):
                nudge[i] += w * v
    norm = sum(x * x for x in nudge) ** 0.5
    if norm < 1e-9:
        return query_emb
    nudge = [x / norm for x in nudge]
    adjusted = [q + alpha * n for q, n in zip(query_emb, nudge)]
    a_norm = sum(x * x for x in adjusted) ** 0.5
    return [x / a_norm for x in adjusted]
from .database import DatabaseManager, get_db_connection
from .fetchers.rss_fetcher import fetch_rss_articles
from .fetchers.scraper import enrich_articles_with_full_text
from .fetchers.eric_fetcher import fetch_eric_for_discipline, DISCIPLINE_ERIC_QUERIES
from .article_filter import ArticleFilter
from .embedder import ArticleEmbedder
from .evaluator import LLMEvaluator
from .personalizer import select_best_articles


class WorkflowManager:
    def __init__(self, teacher_email: str = None, dry_run: bool = False, evaluate_only: bool = False):
        self.teacher_email = teacher_email
        self.dry_run = dry_run
        self.evaluate_only = evaluate_only
        self.run_id = f"Run_{datetime.now():%Y%m%d_%H%M%S}"
        self.conn = None
        self.db = None

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        try:
            self.conn = get_db_connection(CONFIG.DATABASE_URL)
            self.db   = DatabaseManager(self.conn)
            self.db.create_tables()
            self.db.setup_pgvector()
            # Tag legacy articles (pre-discipline-aware) so they're searchable
            self.db.backfill_general_tags()
            logging.info(f"WorkflowManager initialized (run_id={self.run_id}, dry_run={self.dry_run})")
            return True
        except Exception as e:
            logging.critical(f"Initialization failed: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Article ingestion
    # ------------------------------------------------------------------

    def _ingest_articles(self, teachers: list[dict], embedder: ArticleEmbedder) -> None:
        """
        Fetches RSS (tagged 'general') and ERIC per-discipline (tagged with
        the teacher's discipline_key). Embeds every new article immediately
        so vector search works on the next run without re-embedding.
        """
        # --- RSS: practitioner blogs → 'general' pool ---
        rss_raw      = fetch_rss_articles()
        rss_enriched = enrich_articles_with_full_text(rss_raw)
        logging.info(f"RSS: {len(rss_enriched)} articles after full-text scrape.")

        # --- ERIC: one targeted query per distinct discipline in active teachers ---
        discipline_keys = list({
            t['discipline_key'] for t in teachers if t.get('discipline_key')
        })
        eric_by_discipline: dict[str, list[dict]] = {}
        for dk in discipline_keys:
            articles = fetch_eric_for_discipline(dk, max_age_days=CONFIG.MAX_ARTICLE_AGE_DAYS)
            eric_by_discipline[dk] = articles

        total_eric = sum(len(v) for v in eric_by_discipline.values())
        logging.info(
            f"ERIC: {total_eric} articles across {len(discipline_keys)} discipline(s): "
            f"{discipline_keys}"
        )

        # Merge: source_id → (article_dict, set_of_discipline_keys)
        # An article fetched for multiple disciplines gets all tags.
        article_map: dict[str, tuple[dict, set]] = {}
        for art in rss_enriched:
            sid = art['source_id']
            if sid not in article_map:
                article_map[sid] = (art, set())
            article_map[sid][1].add('general')

        for dk, articles in eric_by_discipline.items():
            for art in articles:
                sid = art['source_id']
                if sid not in article_map:
                    article_map[sid] = (art, set())
                article_map[sid][1].add(dk)

        all_articles = [art for art, _ in article_map.values()]
        disc_map     = {sid: discs for sid, (art, discs) in article_map.items()}

        # Filter
        filtered = ArticleFilter().filter(all_articles)
        logging.info(f"Total raw: {len(all_articles)}, after filter: {len(filtered)}")

        # Dedup against DB
        existing     = self.db.get_already_seen_source_ids([a['source_id'] for a in filtered])
        new_articles = [a for a in filtered if a['source_id'] not in existing]
        logging.info(f"Ingestion: {len(new_articles)} truly new articles.")

        if self.dry_run:
            logging.info("[DRY RUN] Skipping DB writes.")
            return

        # Phase 1 — batch upsert articles (committed in chunks of 50, no embedding yet)
        logging.info(f"Ingestion phase 1: upserting {len(new_articles)} articles...")
        id_map = self.db.batch_upsert_articles(new_articles)
        logging.info(f"Ingestion phase 1 complete: {len(id_map)} articles in DB.")

        # Phase 2 — embed each article (API calls outside any transaction)
        logging.info("Ingestion phase 2: embedding articles...")
        emb_pairs: list[tuple[int, list[float]]] = []
        for article in new_articles:
            db_id = id_map.get(article['source_id'])
            if not db_id:
                continue
            emb = embedder.embed_article(article)
            if emb:
                emb_pairs.append((db_id, emb))

        if emb_pairs:
            self.db.batch_update_embeddings(emb_pairs)
        logging.info(f"Ingestion phase 2 complete: {len(emb_pairs)} articles embedded.")

        # Phase 3 — tag disciplines
        logging.info("Ingestion phase 3: tagging disciplines...")
        tag_pairs = [
            (id_map[a['source_id']], dk)
            for a in new_articles
            for dk in disc_map.get(a['source_id'], {'general'})
            if a['source_id'] in id_map
        ]
        if tag_pairs:
            self.db.batch_tag_disciplines(tag_pairs)
        logging.info(f"Ingestion phase 3 complete: {len(tag_pairs)} tags written.")

    # ------------------------------------------------------------------
    # Per-teacher evaluation
    # ------------------------------------------------------------------

    def _process_teacher(
        self,
        teacher: dict,
        embedder: ArticleEmbedder,
        evaluator: LLMEvaluator,
    ) -> int:
        """
        1. Embeds teacher's tailoring_query
        2. pgvector search within their discipline pool
        3. LLM evaluates top candidates
        4. Persists Yes matches
        """
        email          = teacher['email']
        discipline_key = teacher.get('discipline_key')
        logging.info(f"  Processing teacher: {email} (discipline: {discipline_key})")

        # 1. Embed the teacher's specific query
        query_text = (teacher.get('tailoring_query') or '').strip()
        if not query_text:
            query_text = ' '.join(filter(None, [
                teacher.get('discipline', ''),
                teacher.get('current_module', ''),
            ]))

        query_emb  = embedder.embed_text(query_text)
        limit      = CONFIG.MAX_CANDIDATES_PER_TEACHER

        # Apply Rocchio preference nudge from user ratings
        if query_emb:
            query_emb = _apply_rocchio_nudge(
                query_emb,
                self.db.get_rated_article_embeddings(email),
                CONFIG.ROCCHIO_ALPHA,
            )

        # Build prompt-injection context from rated article titles
        rated_titles = self.db.get_rated_article_titles(email)

        # 2a. Vector search (preferred)
        if query_emb:
            candidates = self.db.search_articles_by_vector(
                discipline_key, query_emb,
                limit=limit,
                min_similarity=CONFIG.SIMILARITY_LOW_THRESHOLD,
            )
            logging.info(f"  [{email}] {len(candidates)} candidates from vector search.")
        else:
            # 2b. Keyword fallback when embedding is unavailable
            keywords = [
                teacher.get('discipline', ''),
                teacher.get('current_module', ''),
                teacher.get('tailoring_query', ''),
            ]
            keywords = [k for k in keywords if k]
            candidates = self.db.search_articles_by_keywords(keywords, limit=limit)
            logging.warning(
                f"  [{email}] Embedding unavailable — keyword fallback yielded "
                f"{len(candidates)} candidates."
            )

        if not candidates:
            logging.warning(f"  [{email}] No candidates — discipline pool may be empty.")
            return 0

        # Skip articles already evaluated Yes/No — only process genuinely new ones
        already_evaluated = self.db.get_evaluated_article_ids(email)
        new_candidates = [c for c in candidates if c['_db_id'] not in already_evaluated]
        logging.info(f"  [{email}] {len(new_candidates)} new candidates after skipping {len(already_evaluated)} already evaluated.")

        if not new_candidates:
            logging.info(f"  [{email}] Nothing new to evaluate.")
            return 0

        candidates = new_candidates

        # 3. LLM evaluation — write each result immediately so cancellation preserves progress
        yes_results = []
        with ThreadPoolExecutor(max_workers=CONFIG.MAX_LLM_CONCURRENT_REQUESTS) as ex:
            future_to_art = {
                ex.submit(evaluator.evaluate, art, teacher, rated_titles): art
                for art in candidates
            }
            for future in as_completed(future_to_art):
                art = future_to_art[future]
                try:
                    result = future.result()
                    if result['decision'] == 'Yes':
                        yes_results.append(result)
                    if not self.dry_run:
                        db_id = art.get('_db_id') or art.get('id')
                        if db_id:
                            steps = result.get('action_steps', [])
                            self.db.upsert_match(email, db_id, {
                                "decision":          result['decision'],
                                "summary":           result.get('summary', ''),
                                "action_steps":      _json.dumps(steps) if isinstance(steps, list) else steps,
                                "mission_alignment": result.get('mission_alignment', ''),
                                "similarity_score":  1.0 - art.get('_distance', 1.0),
                            })
                except Exception as e:
                    logging.error(f"  Exception evaluating {art.get('source_id')}: {e}")

        # 4. Cull total Yes articles in DB down to MAX_ARTICLES_PER_TEACHER
        # (DB-aware: accounts for Yes articles from previous partial runs)
        if not self.dry_run:
            downgraded = self.db.cull_yes_articles(email, CONFIG.MAX_ARTICLES_PER_TEACHER)
            if downgraded:
                logging.info(f"  [{email}] Culled {downgraded} excess Yes articles.")

        kept = min(len(yes_results), CONFIG.MAX_ARTICLES_PER_TEACHER)
        logging.info(f"  [{email}]: {len(yes_results)} Yes found this run, {kept} kept after cull.")
        return kept

    # ------------------------------------------------------------------
    # End-of-run cleanup
    # ------------------------------------------------------------------

    def _cleanup_run(self, embedder: ArticleEmbedder) -> None:
        """
        Scans for articles with no embedding and re-embeds them.
        Catches anything dropped by a crash or transient API failure during ingestion.
        Runs at the end of every pipeline execution.
        """
        logging.info("=== Cleanup: scanning for articles with missing embeddings ===")
        missing = self.db.get_articles_missing_embeddings()
        if not missing:
            logging.info("Cleanup: nothing to repair.")
            return

        logging.warning(f"Cleanup: {len(missing)} articles missing embeddings — re-embedding now.")
        emb_pairs: list[tuple[int, list[float]]] = []
        for article in missing:
            emb = embedder.embed_text(
                f"{article['title']}\n\n{(article['full_text'] or '')[:500]}"
            )
            if emb:
                emb_pairs.append((article['id'], emb))

        if emb_pairs:
            self.db.batch_update_embeddings(emb_pairs)

        logging.info(f"Cleanup: repaired {len(emb_pairs)}/{len(missing)} articles.")

    # ------------------------------------------------------------------
    # Embedding health probe
    # ------------------------------------------------------------------

    def _probe_embedder(self, embedder: ArticleEmbedder, retries: int = 3, delay: int = 8) -> None:
        """
        Sends one test embed before the run begins.
        If LM Studio is cold-starting it may need a few seconds to wake;
        we retry a handful of times so the main pipeline sees a warm server.
        """
        for attempt in range(1, retries + 1):
            result = embedder.embed_text("ping")
            if result is not None:
                embedder._failures = 0
                embedder.dead = False
                logging.info(f"Embedding probe OK (attempt {attempt}).")
                return
            if attempt < retries:
                logging.warning(
                    f"Embedding probe failed (attempt {attempt}/{retries}) — "
                    f"waiting {delay}s for LM Studio to start…"
                )
                time.sleep(delay)

        logging.warning(
            "Embedding probe gave up — pipeline will run with keyword-search fallback."
        )

    # ------------------------------------------------------------------
    # Main execute
    # ------------------------------------------------------------------

    def execute(self):
        start = time.time()
        logging.info(f"===== Pipeline started (run_id={self.run_id}) =====")

        try:
            teachers = self.db.fetch_active_teachers(email=self.teacher_email)
            if not teachers:
                logging.warning("No active teachers found. Exiting.")
                return

            embedder  = ArticleEmbedder()
            evaluator = LLMEvaluator()
            self._probe_embedder(embedder)
            evaluator.warm_up(CONFIG.MAX_LLM_CONCURRENT_REQUESTS)

            if self.evaluate_only:
                logging.info("Evaluate-only mode: skipping ingestion.")
            elif self.teacher_email:
                last = self.db.get_last_ingest_time()
                age_days = (datetime.now() - last).days if last else None
                if last and age_days < CONFIG.INGEST_FRESHNESS_DAYS:
                    logging.info(
                        f"Ingestion skipped — full ingest ran {age_days}d ago "
                        f"(threshold: {CONFIG.INGEST_FRESHNESS_DAYS}d). Using existing article pool."
                    )
                else:
                    reason = f"{age_days}d ago" if last else "never"
                    logging.info(f"Last full ingest: {reason} — running ingestion before evaluating teacher.")
                    self._ingest_articles(teachers, embedder)
                    self.db.set_last_ingest_time()
            else:
                self._ingest_articles(teachers, embedder)
                self.db.set_last_ingest_time()

            logging.info(f"Processing {len(teachers)} teacher(s).")
            for teacher in teachers:
                try:
                    self._process_teacher(teacher, embedder, evaluator)
                except Exception as e:
                    logging.error(
                        f"Unhandled exception for teacher {teacher['email']}: {e}", exc_info=True
                    )

            logging.info(f"LLM stats: {evaluator.get_stats()}")
            if embedder.dead:
                logging.warning("Cleanup pass skipped — embedder is offline.")
            else:
                self._cleanup_run(embedder)

        except Exception as e:
            logging.critical(f"Critical pipeline failure: {e}", exc_info=True)
        finally:
            elapsed = time.time() - start
            logging.info(f"===== Pipeline finished in {elapsed:.1f}s =====")
            if self.conn:
                self.conn.close()


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _setup_logging():
    import os
    log_path = CONFIG.LOG_FILE_PATH
    os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)
    from datetime import datetime as _dt
    base, ext = os.path.splitext(log_path)
    timestamped = f"{base}_{_dt.now():%Y%m%d_%H%M%S}{ext}"

    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d — %(message)s')
    level = getattr(logging, CONFIG.LOG_LEVEL, logging.INFO)

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(timestamped, mode='w', encoding='utf-8'),
    ]
    for h in handlers:
        h.setFormatter(fmt)

    logging.basicConfig(level=level, handlers=handlers, force=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pace AI Edu — pipeline runner")
    parser.add_argument("--teacher",       type=str,  default=None, help="Run for a single teacher email.")
    parser.add_argument("--dry-run",       action="store_true",     help="Fetch and evaluate but do not write to DB.")
    parser.add_argument("--evaluate-only", action="store_true",     help="Skip all ingestion; evaluate against existing article pool.")
    args = parser.parse_args()

    _setup_logging()

    wm = WorkflowManager(teacher_email=args.teacher, dry_run=args.dry_run, evaluate_only=args.evaluate_only)
    if not wm.initialize():
        sys.exit(1)
    wm.execute()
