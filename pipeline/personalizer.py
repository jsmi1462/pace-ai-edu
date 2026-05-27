import json

def select_best_articles(matched_articles, max_count=5):
    """
    Selects the best articles from a list of matched articles.
    Articles should be sorted by similarity_score or some other metric.
    
    Args:
        matched_articles (list): List of dicts, each with 'similarity_score', 'article_id', etc.
        max_count (int): Maximum number of articles to return.
    """
    # Sort by similarity score descending
    sorted_articles = sorted(matched_articles, key=lambda x: x.get('similarity_score', 0), reverse=True)
    
    # Return top N
    return sorted_articles[:max_count]
