import logging
from collections import defaultdict
from datetime import date, timedelta

from .config import CONFIG


class ArticleFilter:
    """Programmatic pre-filter: removes spam, ads, and stale content before LLM evaluation."""

    MIN_TEXT_LENGTH = 150   # characters; articles shorter than this are likely stub entries

    def filter(self, articles: list[dict]) -> list[dict]:
        kept, counts = [], defaultdict(int)

        for article in articles:
            title_lower = (article.get('title') or '').lower()
            text_lower  = (article.get('full_text') or '').lower()
            combined    = title_lower + ' ' + text_lower

            # Must have a title and some body text
            if not article.get('title') or not article.get('url'):
                counts['no_title_or_url'] += 1
                continue

            if len(article.get('full_text') or '') < self.MIN_TEXT_LENGTH:
                counts['too_short'] += 1
                continue

            # Exclude promotional / non-editorial content
            # Only check the title — exclusion keywords in body text produce too many
            # false positives from site footers and sidebar widgets.
            if any(kw in title_lower for kw in CONFIG.EXCLUSION_KEYWORDS):
                counts['exclusion_keyword'] += 1
                continue

            kept.append(article)

        logging.info(
            f"ArticleFilter: {len(kept)}/{len(articles)} kept. "
            f"Exclusions: {dict(counts)}"
        )
        return kept
