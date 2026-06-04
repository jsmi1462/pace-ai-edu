"""
ERIC API fetcher — Education Resources Information Center.
Free, no API key, 2M+ peer-reviewed education articles.
API docs: https://api.ies.ed.gov/eric/

Articles are fetched per discipline using targeted queries. Deduplication
against already-ingested articles is handled by the database layer.
"""

import hashlib
import html
import logging
import time
from datetime import date, datetime

import requests

from ..config import CONFIG

ERIC_API_URL = "https://api.ies.ed.gov/eric/"

# Targeted ERIC query per Pace Academy discipline key.
# Each query is tuned to return peer-reviewed literature directly relevant
# to that discipline's teaching practice.
DISCIPLINE_ERIC_QUERIES: dict[str, str] = {
    # Lower School
    "ls_homeroom":        "elementary K-5 literacy reading writing mathematics integrated classroom instruction",
    "ls_math":            "elementary school mathematics number sense operations problem solving K-5",
    "ls_science":         "elementary science inquiry hands-on STEM primary school",
    "ls_steam":           "elementary STEAM design thinking maker technology engineering primary school",
    "ls_world_language":  "elementary Spanish world language acquisition second language young learners",
    "ls_arts":            "elementary visual arts music arts integration primary school",
    "ls_pe":              "elementary physical education movement health wellness fitness K-5",
    "ls_library":         "school library information literacy research skills elementary",
    "ls_learning_support":"elementary reading intervention learning disabilities dyslexia support specialist",
    # Middle School
    "ms_english":         "middle school English language arts literacy writing reading grades 6 7 8",
    "ms_math":            "middle school mathematics algebra fractions ratios geometry problem solving grades 6 7 8",
    "ms_science":         "middle school science life earth physical inquiry laboratory grades 6 7 8",
    "ms_history":         "middle school social studies history civics geography adolescent",
    "ms_world_language":  "middle school world language French Spanish Latin acquisition adolescent",
    "ms_pe":              "middle school physical education adolescent health wellness fitness",
    "ms_steam":           "middle school STEAM robotics engineering programming coding design",
    "ms_arts":            "middle school visual arts music band chorus performance arts education",
    "ms_debate":          "middle school debate argumentation critical thinking public speaking rhetoric",
    # Upper School
    "us_english":         "high school English literature composition AP writing rhetoric analysis",
    "us_math":            "high school mathematics calculus statistics precalculus AP algebra",
    "us_science":         "high school science biology chemistry physics AP laboratory inquiry",
    "us_history":         "high school history social studies AP United States world European",
    "us_world_language":  "high school world language Spanish French Latin AP acquisition fluency",
    "us_cs":              "high school computer science programming AP algorithms robotics data structures",
    "us_arts":            "high school visual arts performing theater music studio AP",
    "us_social_science":  "high school economics psychology sociology debate elective social science",
    "us_learning_support":"high school academic support learning differences study skills college preparation",
    # Cross-division
    "global_leadership":  "global education international competency cross-cultural service learning",
    "counseling":         "school counseling social emotional learning adolescent mental health SEL",
}

# Publication types worth keeping (peer-reviewed research and practitioner reports)
GOOD_PUB_TYPES = {
    "journal articles",
    "reports - research",
    "reports - descriptive",
    "reports - evaluative",
    "dissertations/theses",
    "information analyses",
}


def _parse_date(year_str) -> date | None:
    if not year_str:
        return None
    try:
        return datetime(int(str(year_str)[:4]), 1, 1).date()
    except Exception:
        return None


def _is_recent(pub_date: date | None, max_age_days: int) -> bool:
    if pub_date is None:
        return False  # reject if we can't determine age
    return (date.today() - pub_date).days <= max_age_days


def fetch_eric_for_discipline(
    discipline_key: str,
    max_results: int = None,
    max_age_days: int = None,
) -> list[dict]:
    """Fetches articles for a discipline from ERIC. DB layer handles deduplication."""
    if max_results is None:
        max_results = CONFIG.ERIC_MAX_PER_QUERY
    if max_age_days is None:
        max_age_days = CONFIG.MAX_ARTICLE_AGE_DAYS

    query = DISCIPLINE_ERIC_QUERIES.get(discipline_key)
    if not query:
        logging.warning(f"No ERIC query defined for discipline '{discipline_key}'")
        return []

    logging.info(f"ERIC fetching [{discipline_key}]: '{query[:60]}...'")
    seen_ids: set[str] = set()
    try:
        articles = _fetch_query(query, max_results, max_age_days, seen_ids)
        time.sleep(0.5)
    except Exception as e:
        logging.error(f"ERIC fetch failed [{discipline_key}]: {e}")
        articles = []

    logging.info(f"ERIC [{discipline_key}]: {len(articles)} articles")
    return articles

def _fetch_query(
    query: str,
    max_results: int,
    max_age_days: int,
    seen_ids: set[str],
) -> list[dict]:
    """Fetches up to max_results articles for a single ERIC query, with pagination."""
    articles = []
    page_size = min(100, max_results)
    start = 0

    while len(articles) < max_results:
        params = {
            "search":  query,
            "rows":    page_size,
            "start":   start,
            "fields":  "id,title,description,author,source,publicationdateyear,publicationtype,subject,educationlevel,url",
            "format":  "json",
        }
        try:
            resp = requests.get(ERIC_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logging.warning(f"ERIC API error (start={start}): {e}")
            break

        docs = data.get("response", {}).get("docs", [])
        if not docs:
            break

        for doc in docs:
            eric_id = doc.get("id", "")
            if not eric_id or eric_id in seen_ids:
                continue

            pub_types = [pt.lower() for pt in (doc.get("publicationtype") or [])]
            if pub_types and not any(gt in pub_types for gt in GOOD_PUB_TYPES):
                continue

            pub_date = _parse_date(doc.get("publicationdateyear"))
            if not _is_recent(pub_date, max_age_days):
                continue

            abstract = (doc.get("description") or "").strip()
            if len(abstract) < 100:
                continue

            seen_ids.add(eric_id)
            url = doc.get("url") or f"https://eric.ed.gov/?id={eric_id}"
            source_id = hashlib.sha256(eric_id.encode()).hexdigest()[:32]
            authors = doc.get("author") or []
            authors_str = ", ".join(authors) if isinstance(authors, list) else str(authors)

            articles.append({
                "source_id":        source_id,
                "source":           "ERIC",
                "title":            html.unescape((doc.get("title") or "").strip()),
                "full_text":        abstract,
                "authors":          authors_str,
                "publication_date": pub_date,
                "url":              url,
            })

            if len(articles) >= max_results:
                break

        start += len(docs)
        if start >= data.get("response", {}).get("numFound", 0):
            break

    return articles
