"""
WorkflowManager: orchestrates the full pipeline for one run.

Usage:
    python -m pipeline.workflow [--teacher email@paceacademy.edu] [--dry-run]
"""

import logging
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .config import CONFIG
from .database import DatabaseManager, get_db_connection
from .fetchers.rss_fetcher import fetch_rss_articles
from .fetchers.scraper import enrich_articles_with_full_text
from .fetchers.eric_fetcher import fetch_eric_articles, fetch_eric_for_teacher
from .article_filter import ArticleFilter
from .embedder import ArticleEmbedder
from .evaluator import LLMEvaluator
from .personalizer import select_best_articles


class WorkflowManager:
    def __init__(self, teacher_email: str = None, dry_run: bool = False):
        self.teacher_email = teacher_email  # None = process all active teachers
        self.dry_run = dry_run
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
            logging.info(f"WorkflowManager initialized (run_id={self.run_id}, dry_run={self.dry_run})")
            return True
        except Exception as e:
            logging.critical(f"Initialization failed: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Article ingestion (shared across all teachers)
    # ------------------------------------------------------------------

    def _ingest_articles(self, teachers: list[dict] = None) -> list[dict]:
        """
        Fetches from all sources (RSS + ERIC broad sweep), deduplicates, filters, and upserts.
        Per-teacher targeting is handled downstream via search_articles_by_keywords().
        Returns article dicts with DB ids.
        """
        # --- RSS: practitioner blogs, enriched with full-text scraping ---
        rss_raw = fetch_rss_articles()
        rss_enriched = enrich_articles_with_full_text(rss_raw)
        logging.info(f"RSS: {len(rss_enriched)} articles after full-text scrape.")

        # --- ERIC: broad sweep of 20 topic queries × up to 200 articles each ---
        eric_broad = fetch_eric_articles(
            max_per_query=CONFIG.ERIC_MAX_PER_QUERY,
            max_age_days=CONFIG.MAX_ARTICLE_AGE_DAYS,
        )

        raw = rss_enriched + eric_broad
        logging.info(
            f"Total raw articles before filter: {len(raw)} "
            f"(RSS={len(rss_enriched)}, ERIC={len(eric_broad)})"
        )

        filtered = ArticleFilter().filter(raw)

        # De-duplicate against what's already in the DB
        source_ids = [a['source_id'] for a in filtered]
        existing   = self.db.get_already_seen_source_ids(source_ids)
        new_articles = [a for a in filtered if a['source_id'] not in existing]
        logging.info(f"Ingestion: {len(filtered)} after filter, {len(new_articles)} truly new.")

        if self.dry_run:
            logging.info("[DRY RUN] Skipping DB writes for articles.")
            for a in new_articles:
                a['_db_id'] = None
            return new_articles

        for article in new_articles:
            article_id = self.db.upsert_article(article)
            article['_db_id'] = article_id

        return new_articles

    # ------------------------------------------------------------------
    # Per-teacher evaluation
    # ------------------------------------------------------------------

    def _process_teacher(
        self,
        teacher: dict,
        new_articles: list[dict],
        embedder: ArticleEmbedder,
        evaluator: LLMEvaluator,
    ) -> int:
        """Runs the full eval pipeline for one teacher."""
        email = teacher['email']
        logging.info(f"  Processing teacher: {email}")

        # 1. Generate Keywords (Task-Specific "Search Query")
        keywords = evaluator.generate_keywords(teacher)
        
        # 2. Search Database for relevant existing articles
        candidate_articles = self.db.search_articles_by_keywords(keywords, limit=20)
        
        # 3. Combine with newly ingested articles (avoiding duplicates)
        seen_ids = {a['source_id'] for a in candidate_articles}
        for a in new_articles:
            if a['source_id'] not in seen_ids:
                candidate_articles.append(a)
                seen_ids.add(a['source_id'])
        
        logging.info(f"  Shortlisted {len(candidate_articles)} candidate articles for evaluation.")

        # 4. Embed teacher profile
        teacher_emb = embedder.embed_teacher_profile(teacher)

        # 5. Embed candidate articles (concurrent)
        articles_with_embeddings: list[tuple[dict, list | None]] = []
        embedding_map: dict[str, list] = {}

        with ThreadPoolExecutor(max_workers=CONFIG.MAX_LLM_CONCURRENT_REQUESTS) as ex:
            future_to_art = {ex.submit(embedder.embed_article, a): a for a in candidate_articles}
            for future in as_completed(future_to_art):
                art = future_to_art[future]
                try:
                    emb = future.result()
                    articles_with_embeddings.append((art, emb))
                    if emb:
                        embedding_map[art['source_id']] = emb
                except Exception as e:
                    logging.warning(f"  Embedding exception for {art.get('source_id')}: {e}")
                    articles_with_embeddings.append((art, None))

        # 6. Similarity pre-filter
        yes_corpus = self.db.fetch_yes_embeddings_for_teacher(email) if not self.dry_run else []

        if teacher_emb:
            for_llm, auto_no = embedder.partition_by_similarity(
                articles_with_embeddings, teacher_emb, yes_corpus, CONFIG.SIMILARITY_LOW_THRESHOLD
            )
            logging.info(
                f"  Similarity filter: {len(for_llm)} → LLM, "
                f"{len(auto_no)} auto-rejected"
            )
            # Persist auto-rejected articles
            if not self.dry_run:
                for art in auto_no:
                    db_id = art.get('_db_id') or art.get('id')
                    if db_id:
                        self.db.upsert_match(email, db_id, {
                            "decision": "No",
                            "summary": "Auto-rejected: similarity below threshold.",
                            "action_steps": "[]",
                            "mission_alignment": "",
                            "similarity_score": art.get('_similarity_score', 0.0),
                        })
                        emb = embedding_map.get(art['source_id'])
                        if emb:
                            self.db.upsert_article_embedding(db_id, emb)
        else:
            for_llm = [art for art, _ in articles_with_embeddings]

        # 7. LLM evaluation (concurrent)
        results = []
        with ThreadPoolExecutor(max_workers=CONFIG.MAX_LLM_CONCURRENT_REQUESTS) as ex:
            future_to_art = {
                ex.submit(evaluator.evaluate, art, teacher): art
                for art in for_llm
            }
            for future in as_completed(future_to_art):
                art = future_to_art[future]
                try:
                    result = future.result()
                    result['article'] = art
                    result['similarity_score'] = art.get('_similarity_score', 0.0)
                    results.append(result)
                except Exception as e:
                    logging.error(f"  Exception evaluating {art.get('source_id')}: {e}", exc_info=True)

        # 8. Cull to top N Yes articles
        yes_results = [r for r in results if r['decision'] == 'Yes']
        culled_results = select_best_articles(yes_results, max_count=CONFIG.MAX_ARTICLES_PER_TEACHER)
        
        to_persist = culled_results + [r for r in results if r['decision'] != 'Yes']

        for result in to_persist:
            art = result['article']
            db_id = art.get('_db_id') or art.get('id')
            if not self.dry_run and db_id:
                import json as _json
                steps = result.get('action_steps', [])
                self.db.upsert_match(email, db_id, {
                    "decision":         result['decision'],
                    "summary":          result.get('summary', ''),
                    "action_steps":     _json.dumps(steps) if isinstance(steps, list) else steps,
                    "mission_alignment": result.get('mission_alignment', ''),
                    "similarity_score": result.get('similarity_score'),
                })
                emb = embedding_map.get(art['source_id'])
                if emb:
                    self.db.upsert_article_embedding(db_id, emb)

        logging.info(f"  {email}: {len(culled_results)} Yes articles (culled) this run.")
        return len(culled_results)

    # ------------------------------------------------------------------
    # Main execute
    # ------------------------------------------------------------------

    def execute(self):
        start = time.time()
        logging.info(f"===== Pipeline started (run_id={self.run_id}) =====")

        try:
            # Load teacher profiles first so ERIC can run targeted queries per teacher
            teachers = self.db.fetch_active_teachers(email=self.teacher_email)
            if not teachers:
                logging.warning("No active teachers found. Exiting.")
                return

            # Shared embedder + evaluator — init first so LLM client is available for
            # ERIC keyword generation during ingestion
            embedder  = ArticleEmbedder()
            evaluator = LLMEvaluator()

            articles = self._ingest_articles(teachers=teachers)
            if not articles:
                logging.warning("No new articles to process. Exiting.")
                return
            logging.info(f"Processing {len(teachers)} teacher(s) against {len(articles)} new articles.")

            for teacher in teachers:
                try:
                    self._process_teacher(teacher, articles, embedder, evaluator)
                except Exception as e:
                    logging.error(
                        f"Unhandled exception for teacher {teacher['email']}: {e}", exc_info=True
                    )

            logging.info(f"LLM stats: {evaluator.get_stats()}")

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
    parser.add_argument("--teacher",  type=str,  default=None, help="Run for a single teacher email.")
    parser.add_argument("--dry-run",  action="store_true",     help="Fetch and evaluate but do not write to DB.")
    args = parser.parse_args()

    _setup_logging()

    wm = WorkflowManager(teacher_email=args.teacher, dry_run=args.dry_run)
    if not wm.initialize():
        sys.exit(1)
    wm.execute()
