import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from newspaper import Article


def scrape_full_text(url: str) -> str | None:
    """Downloads and extracts the full article body from a URL using newspaper4k."""
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text.strip()
        return text if len(text) > 200 else None
    except Exception as e:
        logging.debug(f"Scrape failed for {url}: {e}")
        return None


def enrich_articles_with_full_text(articles: list[dict], max_workers: int = 6) -> list[dict]:
    """
    Takes a list of article dicts and replaces/enriches 'full_text' by scraping each URL.
    Articles that fail to scrape keep their RSS summary as full_text.
    """
    logging.info(f"Scraping full text for {len(articles)} articles (workers={max_workers})...")

    url_to_article = {a['url']: a for a in articles if a.get('url')}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(scrape_full_text, url): url
            for url in url_to_article
        }
        scraped, failed = 0, 0
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                text = future.result()
                if text:
                    url_to_article[url]['full_text'] = text
                    scraped += 1
                else:
                    failed += 1
            except Exception as e:
                logging.debug(f"Scrape exception for {url}: {e}")
                failed += 1

    logging.info(f"Scraping complete: {scraped} enriched, {failed} kept RSS summary.")
    return articles
