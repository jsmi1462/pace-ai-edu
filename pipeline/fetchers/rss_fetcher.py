import hashlib
import logging
from datetime import date, datetime, timedelta

import feedparser

from ..config import CONFIG


def _parse_pub_date(entry) -> date | None:
    """Best-effort date parse from a feedparser entry."""
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        try:
            return date(*entry.published_parsed[:3])
        except Exception:
            pass
    if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        try:
            return date(*entry.updated_parsed[:3])
        except Exception:
            pass
    return None


def _source_name(feed_url: str) -> str:
    """Derive a short human-readable source name from the feed URL."""
    if "edutopia" in feed_url:
        return "Edutopia"
    if "cultofpedagogy" in feed_url:
        return "Cult of Pedagogy"
    if "ascd" in feed_url:
        return "ASCD"
    if "edweek" in feed_url:
        return "Education Week"
    if "middleweb" in feed_url:
        return "MiddleWeb"
    return feed_url.split('/')[2].replace('www.', '')


def fetch_rss_articles(max_age_days: int = None) -> list[dict]:
    """
    Fetches and normalizes articles from all configured RSS feeds.
    Returns a list of article dicts ready for the pipeline.
    """
    if max_age_days is None:
        max_age_days = CONFIG.MAX_ARTICLE_AGE_DAYS

    cutoff = date.today() - timedelta(days=max_age_days)
    all_articles = []

    for feed_url in CONFIG.RSS_FEEDS:
        logging.info(f"Fetching RSS: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo:
                logging.warning(f"RSS parse warning for {feed_url}: {feed.bozo_exception}")

            count = 0
            for entry in feed.entries:
                url = entry.get('link', '')
                if not url:
                    continue

                pub_date = _parse_pub_date(entry)
                if pub_date and pub_date < cutoff:
                    continue

                # Stable, reproducible ID based on URL
                source_id = hashlib.sha256(url.encode()).hexdigest()[:32]

                title = entry.get('title', '').strip()
                # Use the RSS summary as a lightweight abstract; full text scraped separately
                summary = entry.get('summary', '') or entry.get('description', '')

                all_articles.append({
                    "source_id":        source_id,
                    "source":           _source_name(feed_url),
                    "title":            title,
                    "full_text":        summary,  # placeholder; scraper enriches this
                    "authors":          entry.get('author', ''),
                    "publication_date": pub_date,
                    "url":              url,
                })
                count += 1

            logging.info(f"  → {count} articles from {_source_name(feed_url)}")

        except Exception as e:
            logging.error(f"Error fetching RSS feed {feed_url}: {e}", exc_info=True)

    logging.info(f"Total RSS articles fetched: {len(all_articles)}")
    return all_articles
