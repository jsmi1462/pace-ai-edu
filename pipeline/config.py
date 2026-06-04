import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

class Config:
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/pace_ai_edu")

    # LLM (LM Studio or OpenAI-compatible)
    LLM_BASE_URL        = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    LLM_API_KEY         = os.getenv("LLM_API_KEY", "lm-studio")
    LLM_MODEL_NAME      = os.getenv("LLM_MODEL_NAME", "local-model")
    LLM_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL", "nomic-embed-text")
    # Native LM Studio API for thinking/reasoning models (Gemma 4, etc.)
    # When set, chat calls use /api/v1/chat instead of the OpenAI-compatible endpoint
    LLM_NATIVE_API_URL  = os.getenv("LLM_NATIVE_API_URL", "")
    # Round-robin LLM endpoints for distributed evaluation (comma-separated base URLs).
    # Falls back to LLM_BASE_URL if not set.
    # e.g. http://100.104.98.2:1234/v1,http://100.116.114.61:1234/v1
    LLM_ENDPOINTS: list[str] = [
        ep.strip()
        for ep in os.getenv("LLM_ENDPOINTS", "").split(",")
        if ep.strip()
    ] or [os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")]

    # Logging
    LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "logs/pipeline.log")
    LOG_LEVEL     = os.getenv("LOG_LEVEL", "INFO").upper()

    # Pipeline tuning
    SIMILARITY_LOW_THRESHOLD      = float(os.getenv("SIMILARITY_LOW_THRESHOLD", 0.55))
    EMBEDDING_DIMENSIONS          = int(os.getenv("EMBEDDING_DIMENSIONS", 768))
    MAX_LLM_CONCURRENT_REQUESTS   = int(os.getenv("MAX_LLM_CONCURRENT_REQUESTS", 4))
    LLM_RETRY_ATTEMPTS            = int(os.getenv("LLM_RETRY_ATTEMPTS", 2))
    LLM_RETRY_DELAY_SECONDS       = int(os.getenv("LLM_RETRY_DELAY_SECONDS", 5))
    MAX_ARTICLE_AGE_DAYS          = int(os.getenv("MAX_ARTICLE_AGE_DAYS", 180))
    # Rocchio preference nudge — how strongly user ratings bias the query vector (0–1)
    ROCCHIO_ALPHA                 = float(os.getenv("ROCCHIO_ALPHA", 0.5))
    MIN_ARTICLES_PER_TEACHER      = int(os.getenv("MIN_ARTICLES_PER_TEACHER", 3))
    MAX_ARTICLES_PER_TEACHER      = int(os.getenv("MAX_ARTICLES_PER_TEACHER", 7))

    # RSS feeds — confirmed working as of 2026-06
    RSS_FEEDS = [
        f.strip() for f in
        os.getenv(
            "RSS_FEEDS",
            # Practitioner / pedagogy
            "https://www.cultofpedagogy.com/feed/,"
            "https://www.middleweb.com/feed/,"
            "https://www.teachthought.com/feed/,"
            "https://www.gettingsmart.com/feed/,"
            "https://larryferlazzo.edublogs.org/feed/,"
            "https://www.responsiveclassroom.org/feed/,"
            "https://blog.ed.ted.com/feed/,"
            "https://www.coolcatteacher.com/feed/,"
            "https://www.weareteachers.com/feed/,"
            # Research-adjacent / policy
            "https://hechingerreport.org/feed/,"
            "https://www.nwea.org/blog/feed/,"
            "https://www.educationnext.org/feed/,"
            # Subject-area organizations
            "https://www.ncte.org/rss/,"
            # News / current practice
            "https://www.educationdive.com/feeds/news/,"
            "https://www.eschoolnews.com/feed/,"
            "https://www.the74million.org/feed/,"
            "https://mindshift.kqed.org/feed/,"
            "https://www.edsurge.com/rss/"
        ).split(",") if f.strip()
    ]

    # ERIC API settings
    ERIC_MAX_PER_QUERY  = int(os.getenv("ERIC_MAX_PER_QUERY", 2000))  # articles per discipline query
    ERIC_TEACHER_MAX    = int(os.getenv("ERIC_TEACHER_MAX", 100))      # extra targeted fetch per teacher

    # Pace Academy mission statement (injected into every prompt)
    PACE_MISSION = os.getenv(
        "PACE_MISSION",
        "Pace Academy develops curious, ethical, and skilled individuals who are prepared to "
        "make a positive difference in the world through academic excellence, character "
        "development, and a commitment to community."
    )

    # Programmatic filter: exclude articles whose title/body contains these
    EXCLUSION_KEYWORDS = {
        "sponsored", "advertisement", "advertorial", "press release",
        "product review", "affiliate", "giveaway",
    }

CONFIG = Config()
