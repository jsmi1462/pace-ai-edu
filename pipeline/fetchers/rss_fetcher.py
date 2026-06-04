import hashlib
import logging
from datetime import date, timedelta

import feedparser
import requests

from ..config import CONFIG

_HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; PaceEduBot/1.0)'}


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
        source = _source_name(feed_url)
        try:
            resp = requests.get(feed_url, timeout=20, headers=_HEADERS)
            if resp.status_code != 200:
                logging.warning(f"RSS {source}: HTTP {resp.status_code} — skipping")
                continue

            feed = feedparser.parse(resp.content)
            if feed.bozo and not feed.entries:
                logging.warning(f"RSS {source}: parse error, 0 entries — {feed.bozo_exception}")
                continue
            if feed.bozo:
                logging.warning(f"RSS {source}: parse warning — {feed.bozo_exception}")

            count = 0
            skipped_old = 0
            for entry in feed.entries:
                url = entry.get('link', '')
                if not url:
                    continue

                pub_date = _parse_pub_date(entry)
                if pub_date and pub_date < cutoff:
                    skipped_old += 1
                    continue

                source_id = hashlib.sha256(url.encode()).hexdigest()[:32]
                title = entry.get('title', '').strip()
                summary = entry.get('summary', '') or entry.get('description', '')

                all_articles.append({
                    "source_id":        source_id,
                    "source":           source,
                    "title":            title,
                    "full_text":        summary,
                    "authors":          entry.get('author', ''),
                    "publication_date": pub_date,
                    "url":              url,
                })
                count += 1

            if count == 0 and skipped_old > 0:
                logging.info(f"RSS {source}: 0 recent articles ({skipped_old} older than {max_age_days}d)")
            elif count == 0:
                logging.info(f"RSS {source}: 0 articles (feed may be empty or entries have no links)")
            else:
                logging.info(f"RSS {source}: {count} articles")

        except Exception as e:
            logging.error(f"RSS {source} ({feed_url}): {e}")

    logging.info(f"Total RSS articles fetched: {len(all_articles)}")
    return all_articles
