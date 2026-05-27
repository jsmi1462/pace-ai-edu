
# --- Unified Headless Application (v5.1.0 - Resilient Single-Pass) ---
# Refactored by the Lead Software Engineer

from notify import send_alert
from embedder import ArticleEmbedder

import os
import random
import sys
import re
import logging
import json
import io
import time as SCRIPT_TIME_MODULE
import traceback
import argparse
import smtplib
from datetime import date, datetime, timedelta, timezone, time
from xml.etree import ElementTree as ET
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from concurrent.futures import ThreadPoolExecutor, as_completed
from calendar import monthrange

# --- Third-Party Imports ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback for Python < 3.9
    logging.error("zoneinfo module not found. Timezone calculations may be incorrect. Consider 'pip install backports.zoneinfo' on Python < 3.9.")
    ZoneInfo = None

import requests
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor
from psycopg2 import sql, extras as psycopg2_extras
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from openai import OpenAI

# --- Load Environment Variables ---
# Load from a .env file in the same directory as the script.
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

tokenizer = None  # Gemma uses a different tokenizer; character estimation is used instead

# --- Global In-Memory Log Capture ---
log_capture_string = io.StringIO()
string_io_handler = None

# --- Configuration Class ---
class Config:
    """
    Centralized configuration management. Pulls settings from environment variables
    and provides sensible defaults.
    """
    # --- Database ---
    DATABASE_URL = os.getenv("DATABASE_URL")

    # --- PubMed API ---
    PUBMED_USER_EMAIL = os.getenv("PUBMED_USER_EMAIL")
    PUBMED_API_KEY = os.getenv("PUBMED_API_KEY")
    PUBMED_USER_AGENT = os.getenv("PUBMED_USER_AGENT", "JF_ETL_Bot/5.1 (mailto:tech@journalfeed.org; purpose: research digest automation)")
    PUBMED_BASE_URL = "https://pubmed.ncbi.nlm.nih.gov/"
    PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    # --- LLM Provider (OpenAI / Ollama) ---
    OLLAMA_BASE_URL = os.getenv("OLLAMA_API_BASE") # Example: http://localhost:11434/v1
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama") # Default key for Ollama
    OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "mistral-large-latest")

    # --- Logging & Email Alerts ---
    LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "logs/headless_run.log")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    LOG_EMAIL_RECIPIENT = os.getenv("LOG_EMAIL_RECIPIENT")

    # --- ConvertKit (Kit) API & Scheduling ---
    KIT_API_KEY = os.getenv("KIT_API_KEY")
    KIT_BROADCAST_URL = "https://api.convertkit.com/v4/broadcasts"
    KIT_SCHEDULE_TIMEZONE_STR = os.getenv("KIT_SCHEDULE_TIMEZONE_STR", "America/New_York")
    KIT_SCHEDULE_LOCAL_HOUR_START = int(os.getenv("KIT_SCHEDULE_LOCAL_HOUR_START", 9))
    KIT_SCHEDULE_LOCAL_MINUTE_START = int(os.getenv("KIT_SCHEDULE_LOCAL_MINUTE_START", 30))

    # --- Article Fetching & Curation Rules ---
    # Defines the day of the month to run the monthly fetch.
    PUBMED_FETCH_DAY_OF_MONTH = int(os.getenv("PUBMED_FETCH_DAY_OF_MONTH", 2))
    # How many months ago to fetch (1 = previous full month)
    PUBMED_FETCH_MONTHS_AGO = int(os.getenv("PUBMED_FETCH_MONTHS_AGO", 1))
    PUBMED_FETCH_LIMIT = int(os.getenv("PUBMED_FETCH_LIMIT", 5000)) 
    MAX_PUBLICATION_AGE_DAYS = int(os.getenv("MAX_PUBLICATION_AGE_DAYS", 180)) 

    # --- Email Content Rules ---
    MIN_ARTICLES_FOR_KIT_EMAIL = int(os.getenv("MIN_ARTICLES_FOR_KIT_EMAIL", 10)) # Min articles for the *entire month*
    MAX_ARTICLES_FOR_KIT_EMAIL = int(os.getenv("MAX_ARTICLES_FOR_KIT_EMAIL", 200)) # Max articles for the *entire month*

    # --- Embedding & Similarity Pre-filter ---
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "nomic-embed-text")
    EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", 768))
    SIMILARITY_LOW_THRESHOLD = float(os.getenv("SIMILARITY_LOW_THRESHOLD", 0.65))
    ENABLE_SIMILARITY_PREFILTER = os.getenv("ENABLE_SIMILARITY_PREFILTER", "true").lower() == "true"

    # --- LLM & Token Management ---
    LLM_MODEL_CONTEXT_LENGTH = int(os.getenv("LLM_MODEL_CONTEXT_LENGTH", 30000))
    LLM_MAX_TOKENS_INITIAL_EVAL = int(os.getenv("LLM_MAX_TOKENS_INITIAL_EVAL", 1024))
    LLM_MAX_TOKENS_SELECTION = int(os.getenv("LLM_MAX_TOKENS_SELECTION", 2048))
    CHARS_PER_TOKEN_ESTIMATE = int(os.getenv("CHARS_PER_TOKEN_ESTIMATE", 4))
    MAX_LLM_CONCURRENT_REQUESTS = int(os.getenv("MAX_LLM_CONCURRENT_REQUESTS", 10))
    LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", 2))
    LLM_RETRY_DELAY_SECONDS = int(os.getenv("LLM_RETRY_DELAY_SECONDS", 5))

    # --- Programmatic Filtering Rules ---
    EXCLUDED_PUB_TYPES_LOWER = {
        "animal", "letter", "comment", "editorial", "news", "retraction of publication",
        "patient education handout", "historical article", "biography", "directory",
        "dictionary", "retracted publication", "consensus development conference",
        "consensus development conference, nih", "introductory journal article",
        "festschrift", "congress", "interview", "lecture", "legal case", "legal cases",
        "periodical index", "scientific integrity review", "bibliography", "classical article",
        "case report", "case reports", "autobiography", "newspaper article", "reply",
        "erratum", "correction", "corrected and republished article", "personal narrative",
        "poster", "technical report", "government publication", "academic dissertation",
        "duplicate publication", "expression of concern", "in memoriam", "obituary",
        "proceeding", "proceedings", "published erratum", "webcast", "video-audio media",
    }
    EXCLUSION_KEYWORDS_LOWER = {
        "murine", "rodent", "mouse", "mice", "canine", "feline", "bovine", "ovine",
        "porcine", "zebrafish", "drosophila", "animal model", "veterinary",
    }

CONFIG = Config()

# --- Pydantic Validation Model ---
class LLMInitialDecision(BaseModel):
    """Ensures the LLM's initial evaluation response conforms to the expected JSON structure."""
    decision: str = Field(..., pattern=r"^(Yes|No)$")
    details: str

    @field_validator('details')
    @classmethod
    def details_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("details field cannot be empty or just whitespace")
        return value.strip()

# --- Utility Functions ---
def setup_logging(log_file_path):
    """Configures logging to file, console, and an in-memory string for email alerts."""
    global string_io_handler

    log_level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}
    effective_log_level = log_level_map.get(CONFIG.LOG_LEVEL, logging.INFO)
    
    log_dir = os.path.dirname(log_file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    detailed_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(funcName)s - %(message)s')
    console_formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')

    # Start with a clean slate of handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    handlers_list = []
    
    # Configure file handler (writes to a new file for each run)
    file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(detailed_formatter)
    handlers_list.append(file_handler)

    # Configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    handlers_list.append(console_handler)

    # Configure in-memory handler for the log email
    string_io_handler = logging.StreamHandler(log_capture_string)
    string_io_handler.setFormatter(detailed_formatter)
    handlers_list.append(string_io_handler)

    logging.basicConfig(level=effective_log_level, handlers=handlers_list, force=True)

    logging.info(f"--- Logging configured (Level: {CONFIG.LOG_LEVEL}) ---")
    if 'mailto:your-email@example.com' in CONFIG.PUBMED_USER_AGENT:
        logging.critical("CRITICAL: Default PubMed User Agent is being used. Update PUBMED_USER_AGENT in .env with a real contact email!")

def format_nlm_citation(article_data):
    """Formats article data into a standard NLM citation string."""
    authors_str = article_data.get('authors_str', "No Authors Listed") + "."
    title = (article_data.get('title', 'No Title Available').strip() or "No Title Available")
    if not title.endswith(('.', '?', '!')): title += "."

    journal_abbr = (article_data.get('journal_iso_abbr') or article_data.get('journal', 'Unknown Journal')).strip().removesuffix('.')
    
    # Handle cases where publication_date might be a string or a date object
    pub_date = article_data.get('publication_date')
    date_str = ""
    if isinstance(pub_date, date):
        date_str = pub_date.strftime("%Y %b %d")
    elif isinstance(pub_date, str):
        date_str = pub_date # Assume it's pre-formatted if a string
    
    # Fallback to dictionary parts if they exist
    if not date_str:
        pub_date_dict = article_data.get('pub_date_dict', {})
        year = pub_date_dict.get('Year', '')
        month_str = pub_date_dict.get('Month', '')
        day = pub_date_dict.get('Day', '')
        
        date_str_part = year
        if month_str:
            try:
                month_abbr = datetime.strptime(str(month_str).zfill(2), "%m").strftime("%b")
                date_str_part += f" {month_abbr}"
            except ValueError:
                date_str_part += f" {month_str}"
        if day: date_str_part += f" {day}"
        date_str = date_str_part.strip()
    
    journal_issue_dict = article_data.get('journal_issue', {})
    volume = journal_issue_dict.get('Volume', '')
    issue = journal_issue_dict.get('Issue', '')
    pages = article_data.get('pagination', '')
    
    journal_details = f"{journal_abbr}."
    if date_str: journal_details += f" {date_str}"
    if volume: journal_details += f";{volume}"
    if issue: journal_details += f"({issue})"
    if pages: journal_details += f":{pages}"
    if not journal_details.endswith('.'): journal_details += "."
    
    doi_str = f"doi: {article_data['doi']}." if article_data.get('doi') else ""
    pmid_str = f"PMID: {article_data['pubmed_id']}." if article_data.get('pubmed_id') else ""
    
    citation = " ".join(part for part in [authors_str, title, journal_details, doi_str, pmid_str] if part)
    return re.sub(r'\s{2,}', ' ', citation).strip()

def get_db_connection(database_url):
    """Establishes and returns a database connection. Exits on failure."""
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except psycopg2.OperationalError as e:
        logging.critical(f"CRITICAL: Could not connect to the database. Check credentials and network. {e}")
        sys.exit(1)

# --- Component Classes ---

class DatabaseManager:
    """Handles all database interactions, using a normalized schema."""
    def __init__(self, conn):
        self.conn = conn

    def setup_pgvector(self) -> bool:
        """Enables the pgvector extension and adds the embedding column. Returns True on success."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(
                    f"ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding vector({CONFIG.EMBEDDING_DIMENSIONS});"
                )
            self.conn.commit()
            logging.info(f"pgvector ready (embedding column: vector({CONFIG.EMBEDDING_DIMENSIONS})).")
            return True
        except Exception as e:
            logging.warning(f"pgvector setup failed — similarity pre-filter will be disabled: {e}")
            self.conn.rollback()
            return False

    def upsert_article_embedding(self, article_id: int, embedding: list[float]) -> None:
        if not article_id or not embedding:
            return
        embedding_str = '[' + ','.join(f'{x:.8f}' for x in embedding) + ']'
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE articles SET embedding = %s::vector WHERE id = %s",
                    (embedding_str, article_id),
                )
            self.conn.commit()
        except Exception as e:
            logging.warning(f"Failed to store embedding for article {article_id}: {e}")
            self.conn.rollback()

    def fetch_yes_corpus_embeddings(self, discipline_id: int) -> list[list[float]]:
        query = """
            SELECT a.embedding::text
            FROM articles a
            JOIN article_evaluations ae ON a.id = ae.article_id
            WHERE ae.discipline_id = %s
              AND ae.decision = 'Yes'
              AND a.embedding IS NOT NULL
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (discipline_id,))
                rows = cur.fetchall()
            result = []
            for (emb_str,) in rows:
                if emb_str:
                    result.append([float(x) for x in emb_str.strip('[]').split(',')])
            return result
        except Exception as e:
            logging.warning(f"Failed to fetch Yes corpus embeddings for discipline {discipline_id}: {e}")
            return []

    def create_tables(self):
        """Ensures that the required database tables exist."""
        commands = (
            """
            CREATE TABLE IF NOT EXISTS disciplines (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                query TEXT NOT NULL,
                heuristic TEXT,
                convertkit_tag_id INTEGER,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                pubmed_id INTEGER UNIQUE NOT NULL,
                title TEXT,
                abstract TEXT,
                authors TEXT,
                journal VARCHAR(255),
                publication_date DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS article_evaluations (
                id SERIAL PRIMARY KEY,
                article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                discipline_id INTEGER NOT NULL REFERENCES disciplines(id) ON DELETE CASCADE,
                decision VARCHAR(50),
                summary TEXT,
                rationale TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                date_evaluated DATE DEFAULT CURRENT_DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (article_id, discipline_id)
            )
            """
        )
        try:
            with self.conn.cursor() as cur:
                for command in commands:
                    cur.execute(command)
            self.conn.commit()
            logging.info("Database tables ensured to exist.")
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(f"Error creating tables: {error}")
            self.conn.rollback()
            raise

    def upsert_article(self, article_data):
        """
        Inserts a new article or updates an existing one based on pubmed_id.
        This is the core of the new de-duplication strategy.
        """
        sql_command = sql.SQL("""
            INSERT INTO articles (pubmed_id, title, abstract, authors, journal, publication_date)
            VALUES (%(pubmed_id)s, %(title)s, %(abstract)s, %(authors)s, %(journal)s, %(publication_date)s)
            ON CONFLICT (pubmed_id) DO UPDATE SET
                title = EXCLUDED.title, abstract = EXCLUDED.abstract, authors = EXCLUDED.authors,
                journal = EXCLUDED.journal, publication_date = EXCLUDED.publication_date,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
        """)
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql_command, {
                    'pubmed_id': article_data['pubmed_id'], 'title': article_data['title'], 
                    'abstract': article_data['abstract'], 'authors': ", ".join(article_data.get('authors', [])), 
                    'journal': article_data['journal'], 'publication_date': article_data.get('publication_date')
                })
                article_id = cur.fetchone()[0]
                self.conn.commit()
                return article_id
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(f"DB Error upserting article {article_data.get('pubmed_id')}: {error}", exc_info=True)
            self.conn.rollback()
            return None

    def upsert_evaluation(self, article_id, discipline_id, eval_data):
        """Inserts or updates an evaluation and returns its ID."""
        sql_command = sql.SQL("""
            INSERT INTO article_evaluations (article_id, discipline_id, decision, summary, rationale, status, date_evaluated)
            VALUES (%(article_id)s, %(discipline_id)s, %(decision)s, %(summary)s, %(rationale)s, 'pending', CURRENT_DATE)
            ON CONFLICT (article_id, discipline_id) DO UPDATE SET
                decision = EXCLUDED.decision, summary = EXCLUDED.summary, rationale = EXCLUDED.rationale,
                status = 'pending', updated_at = CURRENT_TIMESTAMP, date_evaluated = CURRENT_DATE
            WHERE article_evaluations.status NOT LIKE 'kit_%%'                  
            RETURNING id;
        """)
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql_command, {
                    'article_id': article_id, 'discipline_id': discipline_id,
                    'decision': eval_data['decision'], 'summary': eval_data.get('summary_text'),
                    'rationale': eval_data.get('initial_rationale_text')
                })
                eval_id = cur.fetchone()[0]
                self.conn.commit()
                return eval_id
        except (Exception, psycopg2.DatabaseError) as error:
            logging.error(f"DB Error upserting evaluation for article_id {article_id}: {error}", exc_info=True)
            self.conn.rollback()
            return None
    
    def fetch_active_queries(self, target_discipline_name=None):
        """Fetches all active disciplines or a single one by name."""
        query = "SELECT id, name AS discipline_name, query, heuristic, convertkit_tag_id FROM disciplines WHERE is_active = TRUE"
        params = []
        if target_discipline_name:
            query += " AND name = %s"
            params.append(target_discipline_name)
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def get_processed_pmids_for_discipline(self, discipline_id, pmids_to_check):
        """
        NEW: Checks the 'article_evaluations' table for a list of PMIDs
        against a *specific discipline_id*.
        """
        if not pmids_to_check or not discipline_id:
            return set()
        
        query = """
            SELECT DISTINCT a.pubmed_id
            FROM article_evaluations ae
            JOIN articles a ON ae.article_id = a.id
            WHERE ae.discipline_id = %s AND a.pubmed_id = ANY(%s);
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (discipline_id, pmids_to_check))
            return {int(row[0]) for row in cur.fetchall()}

    def fetch_approved_articles_by_date_range(self, discipline_id, start_date, end_date):
        """
        Fetches all 'Yes' articles for a discipline within a specific publication date range.
        Used to combine newly processed articles with previously processed ones (from overlapping runs).
        """
        query = sql.SQL("""
            SELECT
                a.pubmed_id, a.title, a.authors, a.journal, a.abstract, a.publication_date,
                ae.summary AS llm_one_line_summary, ae.id AS eval_id
            FROM articles a
            JOIN article_evaluations ae ON a.id = ae.article_id
            WHERE ae.discipline_id = %s
              AND ae.decision = 'Yes'
              AND a.publication_date BETWEEN %s AND %s
            ORDER BY a.publication_date DESC;
        """)
        try:
            with self.conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
                cur.execute(query, (discipline_id, start_date, end_date))
                articles = []
                for row in cur.fetchall():
                    art_dict = dict(row)
                    # format authors for consistency
                    art_dict['authors_str'] = art_dict['authors'] 
                    articles.append(art_dict)
                return articles
        except Exception as e:
            logging.error(f"DB error in fetch_approved_articles_by_date_range: {e}", exc_info=True)
            return []
    def update_evaluation_summary(self, eval_id, summary_text):
        """Updates ONLY the summary for an existing evaluation."""
        if not eval_id or not summary_text: return
        query = "UPDATE article_evaluations SET summary = %s WHERE id = %s"
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (summary_text, eval_id))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Failed to update summary for eval_id {eval_id}: {e}")
            self.conn.rollback()    
    def update_evaluation_status_bulk(self, eval_ids, status_msg):
        """Updates the status of multiple evaluations at once."""
        if not eval_ids: return
        query = "UPDATE article_evaluations SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = ANY(%s);"
        with self.conn.cursor() as cur:
            cur.execute(query, (status_msg, eval_ids))
        self.conn.commit()
        logging.info(f"Updated status to '{status_msg}' for {len(eval_ids)} evaluations.")
    
    def fetch_articles_for_kit_email(self, discipline_names_list):
        """
        Fetches 'Yes'/'pending' articles. Used by the db-only mode.
        NOTE: Schema strictly adhered to (ae.status, not ae.email_status).
        """
        articles_for_email = []
        if not discipline_names_list:
            return articles_for_email
        
        query = sql.SQL("""
            SELECT
                a.pubmed_id,
                a.title,
                a.authors,
                a.journal,
                a.abstract,
                a.publication_date,
                ae.summary AS llm_one_line_summary,
                d.name AS source_query_term,
                ae.id AS eval_id
            FROM articles a
            JOIN article_evaluations ae ON a.id = ae.article_id
            JOIN disciplines d ON ae.discipline_id = d.id
            WHERE ae.status = 'pending'
              AND ae.decision = 'Yes'
              AND d.name = ANY(%s)
            ORDER BY ae.date_evaluated DESC, ae.id DESC;
        """)
        try:
            with self.conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
                cur.execute(query, (discipline_names_list,))
                for row in cur.fetchall():
                    article_dict = dict(row)
                    
                    article_dict['authors_str'] = article_dict['authors']
                    article_dict['pubmed_url'] = f"{CONFIG.PUBMED_BASE_URL}{article_dict['pubmed_id']}/"
                    
                    pub_date_obj = article_dict.get('publication_date')
                    article_dict['pub_date_dict'] = {
                        "Year": str(pub_date_obj.year),
                        "Month": str(pub_date_obj.month),
                        "Day": str(pub_date_obj.day)
                    } if pub_date_obj else {}
                    
                    articles_for_email.append(article_dict)
        except Exception as e:
            logging.error(f"DB error in fetch_articles_for_kit_email: {e}", exc_info=True)
        return articles_for_email

class PubMedFetcher:
    """Handles fetching and parsing article data from the PubMed API."""
    def __init__(self):
        self.headers = {"User-Agent": CONFIG.PUBMED_USER_AGENT}

    def _parse_article(self, xml_article):
        """Parses an individual article's XML into a dictionary."""
        try:
            pmid = xml_article.find(".//PMID").text
            title_node = xml_article.find(".//ArticleTitle")
            title = "".join(title_node.itertext()).strip() if title_node is not None else ""
            
            journal_node = xml_article.find(".//Journal")
            journal = journal_node.findtext(".//Title", "N/A")
            journal_iso = journal_node.findtext(".//ISOAbbreviation", journal)
            
            # Robust date parsing
            pub_date_node = xml_article.find(".//PubDate")
            year_str = pub_date_node.findtext("Year")
            month_str = pub_date_node.findtext("Month") # Could be month name or number
            day_str = pub_date_node.findtext("Day")
            publication_date = None

            if year_str:
                try:
                    # Attempt YYYY-Mon-DD or YYYY-MM-DD
                    if month_str and day_str:
                        try:
                            publication_date = datetime.strptime(f"{year_str}-{month_str}-{day_str}", "%Y-%b-%d").date()
                        except ValueError:
                            publication_date = datetime.strptime(f"{year_str}-{month_str}-{day_str}", "%Y-%m-%d").date()
                    # Attempt YYYY-Mon or YYYY-MM
                    elif month_str:
                        try: # Try month abbreviation (e.g., Jan, Feb)
                            publication_date = datetime.strptime(f"{year_str}-{month_str}", "%Y-%b").date()
                        except ValueError: # Try month number (e.g., 01, 12)
                            publication_date = datetime.strptime(f"{year_str}-{month_str}", "%Y-%m").date()
                    # Fallback to just Year, defaulting to Jan 1
                    else:
                        publication_date = datetime.strptime(year_str, "%Y").date().replace(month=1, day=1) # Default to Jan 1
                except ValueError:
                    # If even the year itself is malformed, log and keep as None
                    logging.warning(f"Could not parse any part of publication date for PMID {pmid}: Year='{year_str}', Month='{month_str}', Day='{day_str}'. Storing as null.")
                    publication_date = None
            
            authors_list = [f"{auth.findtext('LastName', '')} {auth.findtext('Initials', '')}".strip()
                            for auth in xml_article.findall(".//Author") if auth.findtext('LastName')]
            
            abstract_node = xml_article.find(".//Abstract")
            abstract = "".join(abstract_node.itertext()).strip() if abstract_node is not None else ""

            pub_type_list = [pt.text for pt in xml_article.findall(".//PublicationType")]

            return {
                "pubmed_id": int(pmid), "title": title, "journal": journal_iso,
                "publication_date": publication_date, "authors_str": ", ".join(authors_list),
                "authors": authors_list, "abstract": abstract, "pub_types": pub_type_list
            }
        except Exception as e:
            logging.error(f"Error parsing article XML for PMID {pmid if 'pmid' in locals() else 'unknown'}: {e}", exc_info=True)
            return None

    def fetch_articles(self, search_term, discipline_name="Unknown", run_date=None):
        """
        REFACTORED: Fetches articles for the *previous full month*.
        """
        try:
            # Determine date range for the query based on the new monthly logic
            if not run_date:
                run_date = date.today()
            
            # Go to the first day of the current month
            first_of_this_month = run_date.replace(day=1)
            # Subtract one day to get the last day of the *previous* month
            end_date_val = first_of_this_month - timedelta(days=1)
            # Go to the first day of that *previous* month
            start_date_val = end_date_val.replace(day=1)

            logging.info(f"Querying PubMed for '{discipline_name}': Fetching previous full month '{start_date_val:%Y-%m-%d} to {end_date_val:%Y-%m-%d}'")

            date_filter = f"({start_date_val:%Y/%m/%d}[Date - Publication]:{end_date_val:%Y/%m/%d}[Date - Publication])"
            final_query = f"({search_term}) AND {date_filter}"

            # Step 1: ESearch to get PMIDs using the history server
            esearch_params = {"db": "pubmed", "retmode": "xml"}
            if CONFIG.PUBMED_API_KEY:
                esearch_params["api_key"] = CONFIG.PUBMED_API_KEY

            esearch_data = {
                "term": final_query,
                "retmax": str(CONFIG.PUBMED_FETCH_LIMIT),
                "sort": "pub date",
                "usehistory": "y"
            }
            
            esearch_response = requests.post(CONFIG.PUBMED_ESEARCH_URL, headers=self.headers, params=esearch_params, data=esearch_data, timeout=60)
            esearch_response.raise_for_status()
            
            esearch_root = ET.fromstring(esearch_response.content)
            id_count = int(esearch_root.findtext(".//Count", "0"))
            if id_count == 0:
                logging.warning(f"No PMIDs from ESearch for '{discipline_name}'. Full query was: {final_query}")
                return []

            web_env = esearch_root.findtext(".//WebEnv")
            query_key = esearch_root.findtext(".//QueryKey")
            if not web_env or not query_key:
                logging.error(f"Could not get History Server details for '{discipline_name}'.")
                return []
            
            logging.info(f"ESearch for '{discipline_name}' found {id_count} articles. Fetching details...")

            # Step 2: EFetch to get full article details
            efetch_params = {
                "db": "pubmed", "retmode": "xml", "WebEnv": web_env, "query_key": query_key,
                "retmax": str(id_count), "api_key": CONFIG.PUBMED_API_KEY
            }
            efetch_response = requests.get(CONFIG.PUBMED_EFETCH_URL, params=efetch_params, headers=self.headers, timeout=180)
            efetch_response.raise_for_status()
            efetch_root = ET.fromstring(efetch_response.content)

            articles = [self._parse_article(article_xml) for article_xml in efetch_root.findall(".//PubmedArticle")]
            valid_articles = [art for art in articles if art]
            logging.info(f"Fetched & parsed {len(valid_articles)} articles for '{discipline_name}'.")
            return valid_articles

        except requests.exceptions.HTTPError as e:
            logging.error(f"PubMed API HTTP Error for '{discipline_name}': {e.response.status_code} - {e.response.text[:500]}", exc_info=True)
        except Exception as e:
            logging.error(f"Error fetching from PubMed for '{discipline_name}': {e}", exc_info=True)
        return []

class ArticleFilter:
    """Applies programmatic filters to exclude certain articles before LLM evaluation."""
    def __init__(self, config):
        self.excluded_pub_types = config.EXCLUDED_PUB_TYPES_LOWER
        self.exclusion_keywords = config.EXCLUSION_KEYWORDS_LOWER
        self.max_age_days = config.MAX_PUBLICATION_AGE_DAYS
        self.today = date.today() # Cache today's date for age check

    def filter_articles(self, articles, discipline_name):
        logging.info(f"Programmatic Prefiltering {len(articles)} articles for '{discipline_name}'...")
        filtered_articles = []
        exclusion_counts = defaultdict(int)
        for article in articles:
            if not article.get('abstract'):
                exclusion_counts['no_abstract'] += 1
                continue
            title_lower = article['title'].lower()
            abstract_lower = article['abstract'].lower()

            if any(keyword in title_lower or keyword in abstract_lower for keyword in self.exclusion_keywords):
                exclusion_counts['exclusion_keyword'] += 1
                continue

            # Check publication types
            is_excluded_type = False
            for pub_type in article.get('pub_types', []):
                if pub_type.lower() in self.excluded_pub_types:
                    exclusion_counts[f"excluded_pub_type: {pub_type.lower()}"] += 1
                    is_excluded_type = True
                    break
            if is_excluded_type:
                continue

            filtered_articles.append(article)
        
        logging.info(f"Prefiltering for '{discipline_name}' complete. Kept {len(filtered_articles)} of {len(articles)}.")
        if exclusion_counts:
            logging.info(f"Exclusion counts for '{discipline_name}': {dict(exclusion_counts)}")
        return filtered_articles

class LLMEvaluator:
    """
    Handles all interactions with the LLM, including initial evaluation
    and final selection (if list is too long).
    """
    def __init__(self, config):
        self.config = config
        self.client = None
        self._initialize_client()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.request_counts = defaultdict(int)

    def _initialize_client(self):
        """Initializes the OpenAI client for either an Ollama or official OpenAI endpoint."""
        if self.config.OLLAMA_BASE_URL:
            self.client = OpenAI(base_url=self.config.OLLAMA_BASE_URL, api_key=self.config.OPENAI_API_KEY)
            logging.info(f"LLM client initialized for Ollama-compatible endpoint: {self.config.OLLAMA_BASE_URL}")
        else:
            self.client = OpenAI(api_key=self.config.OPENAI_API_KEY)
            logging.info("LLM client initialized for official OpenAI endpoint.")

    def _get_token_count(self, text=""):
        if not text: return 0
        return max(1, len(str(text)) // self.config.CHARS_PER_TOKEN_ESTIMATE)

    def _call_llm_api(self, pmid, user_prompt, system_message, max_tokens):
        last_error = "Unknown failure after all retries"
        for attempt in range(self.config.LLM_RETRY_ATTEMPTS + 1):
            try:
                messages = []
                if system_message: messages.append({"role": "system", "content": system_message})
                messages.append({"role": "user", "content": user_prompt})

                completion = self.client.chat.completions.create(
                    model=self.config.OPENAI_MODEL_NAME,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.1,
                )

                if not completion.choices or not completion.choices[0].message:
                    logging.error(f"PMID {pmid}: LLM response missing choices or message. Full completion: {completion.to_dict() if hasattr(completion, 'to_dict') else str(completion)}")
                    raise ValueError("LLM response did not contain expected choices/message structure.")

                response_text = completion.choices[0].message.content.strip()
                logging.debug(f"PMID {pmid}: Raw LLM API response text: '{response_text}'")

                if completion.usage:
                    self.total_prompt_tokens += completion.usage.prompt_tokens
                    self.total_completion_tokens += completion.usage.completion_tokens

                return response_text
            except ValueError as ve:
                last_error = str(ve)
                logging.error(f"PMID {pmid}: LLM response structure validation failed. Error: {last_error}")
                return f"LLM Error - {last_error}"
            except Exception as e:
                last_error = str(e)
                if "context_length_exceeded" in last_error.lower() or "context window" in last_error.lower():
                    logging.error(f"PMID {pmid}: Context Length Exceeded. Cannot retry.")
                    return "LLM Error - Context Length Exceeded"

                if attempt < self.config.LLM_RETRY_ATTEMPTS:
                    delay = self.config.LLM_RETRY_DELAY_SECONDS
                    logging.warning(f"PMID {pmid}: LLM call failed ({last_error}). Retrying in {delay}s...")
                    SCRIPT_TIME_MODULE.sleep(delay)

        logging.error(f"PMID {pmid}: LLM API call failed definitively. Last error: {last_error}")
        return f"LLM Error - {last_error}"

    def get_llm_stats(self):
        """Returns a dictionary of token usage and request counts."""
        stats = self.request_counts.copy()
        stats['prompt_tokens'] = self.total_prompt_tokens
        stats['completion_tokens'] = self.total_completion_tokens
        stats['total_tokens'] = self.total_prompt_tokens + self.total_completion_tokens
        return stats

    def get_initial_decision_and_summary(self, article_data, heuristic, discipline_name):
        """Gets the initial 'Yes/No' decision and summary."""
        self.request_counts["initial_eval_requests"] += 1
        pmid = article_data.get('pubmed_id', 'N/A')

        system_prompt = "You are a meticulous medical review AI. Your task is to evaluate a scientific abstract based on a strict heuristic and output a valid JSON object. Do not include any explanatory text outside of the JSON structure."
        user_prompt = (
            f"Review the following article for a {discipline_name} physician audience.\n\n"
            f"**Heuristic:**\n{heuristic}\n\n"
            f"**Article Information:**\n- Title: {article_data.get('title', 'N/A')}\n- Abstract: {article_data.get('abstract', 'N/A')}\n\n"
            f"**Your Task:**\n1.  **Decision**: Decide 'Yes' or 'No'.\n2.  **Details**: If 'Yes', write a one-sentence summary (population, outcome, implication). If 'No', provide a brief reason.\n3.  **Output**: Respond with ONLY a JSON object with two keys: \"decision\" and \"details\".\n\n"
            f"Example Yes: {{\"decision\": \"Yes\", \"details\": \"In a study of 500 adults with diabetes, metformin reduced A1c levels by 1.5% more than placebo, reinforcing its use as a first-line therapy.\"}}\n"
            f"Example No: {{\"decision\": \"No\", \"details\": \"The study is a Phase I trial, which is excluded by the heuristic.\"}}\n\n"
            f"**JSON Output:**"
        )
        response_text = self._call_llm_api(pmid, user_prompt, system_prompt, self.config.LLM_MAX_TOKENS_INITIAL_EVAL)
        if "LLM Error" in response_text:
            return {"decision": "Error", "summary_text": "LLM call failed.", "initial_rationale_text": response_text}

        try:
            cleaned_text = re.sub(r"^\s*```json\s*|\s*```\s*$", "", response_text, flags=re.DOTALL).strip()
            validated_data = LLMInitialDecision.model_validate_json(cleaned_text)
            logging.info(f"PMID {pmid}: LLM evaluation response: {cleaned_text}")
            if validated_data.decision == "Yes":
                return {"decision": "Yes", "summary_text": validated_data.details, "initial_rationale_text": "N/A"}
            else:
                return {"decision": "No", "summary_text": "N/A", "initial_rationale_text": validated_data.details}
        except (json.JSONDecodeError, ValueError) as e:
            logging.warning(f"PMID {pmid}: Initial response failed validation ({e}). Raw text: '{response_text[:300]}'.")
            return {"decision": "Error", "summary_text": "LLM response validation failed.", "initial_rationale_text": f"Validation Error: {e}"}

    def _build_selection_prompt(self, articles, discipline_name, count):
        """Helper method to construct the prompt for final culling."""
        
        candidate_prompts = [f"- PMID: {a.get('pubmed_id')}\n  Title: {a.get('title')}\n  Summary: {a.get('llm_one_line_summary', 'N/A')}\n" for a in articles]

        prompt_instructions = f"You are a medical digest editor for JournalFeed. Your mission is to find the most useful articles for practicing clinicians. From the list below, select the top {count} articles that are the most clinically relevant, actionable, and practice-changing for a {discipline_name} specialist. Prioritize bedside impact over pure novelty."
        final_instructions = f"\n\n**Candidate Articles:**\n{''.join(candidate_prompts)}\n\n**Your Task:**\nReturn ONLY a comma-separated list of the PubMed IDs (PMID) for your final selection.\n\n**Selected PMIDs:**"

        return f"{prompt_instructions}{final_instructions}"
    
    def select_best_articles(self, articles, discipline_name, count):
        """
        Selects the best articles. This is now only used as a final "culling" step
        if the total monthly articles exceeds MAX_ARTICLES_FOR_KIT_EMAIL.
        """
        self.request_counts[f"selection_requests_cull"] += 1
        if not articles or count <= 0: return []
        if len(articles) <= count: return articles # No culling needed

        candidate_articles = list(articles)
        
        # Estimate max articles per call with a generous safety margin
        prompt_overhead_tokens = 2000
        available_tokens = self.config.LLM_MODEL_CONTEXT_LENGTH - self.config.LLM_MAX_TOKENS_SELECTION - prompt_overhead_tokens
        tokens_per_article = 150 # A conservative estimate for a title/summary line
        max_articles_in_prompt = max(1, available_tokens // tokens_per_article)

        if len(candidate_articles) > max_articles_in_prompt:
            logging.warning(f"Candidate list ({len(candidate_articles)}) is too large for a single call. Truncating to {max_articles_in_prompt}.")
            candidate_articles = candidate_articles[:max_articles_in_prompt]

        # Final selection round
        logging.info(f"Running final selection round with {len(candidate_articles)} candidates to pick the top {count}.")
        final_prompt = self._build_selection_prompt(candidate_articles, discipline_name, count)
        selected_pmids_str = self._call_llm_api(f"select-best-{discipline_name}", final_prompt, None, self.config.LLM_MAX_TOKENS_SELECTION)

        if "error" in selected_pmids_str.lower():
            logging.error(f"LLM failed final selection. Falling back to chronological order from candidates.")
            return candidate_articles[:count]

        try:
            ordered_pmids = [int(p) for p in re.findall(r'\d+', selected_pmids_str)]
            article_map = {a.get('pubmed_id'): a for a in candidate_articles}
            selected_articles = [article_map[pmid] for pmid in ordered_pmids if pmid in article_map]
            return selected_articles[:count]
        except Exception as e:
            logging.error(f"Error parsing final LLM selection response: {e}. Falling back to chronological.", exc_info=True)
            return candidate_articles[:count]

class EmailManager:
    """Handles sending SMTP log emails and interacting with the ConvertKit API."""
    def __init__(self, config):
        self.config = config

    def send_log_email(self, run_id, log_contents):
        """Sends the full execution log via SMTP."""
        if not all([self.config.SMTP_SERVER, self.config.SMTP_USER, self.config.SMTP_PASSWORD, self.config.LOG_EMAIL_RECIPIENT]):
            logging.warning("SMTP not fully configured. Skipping log email.")
            return
        
        subject = f"Unified Digest Run Log - {run_id}"
        if "CRITICAL" in log_contents.upper() or "ERROR" in log_contents.upper():
            subject += " - WITH ISSUES"
        else:
            subject += " - SUCCESS"

        msg = MIMEMultipart()
        msg['From'] = self.config.SMTP_USER
        msg['To'] = self.config.LOG_EMAIL_RECIPIENT
        msg['Subject'] = subject
        msg.attach(MIMEText(log_contents, 'plain', 'utf-8'))

        try:
            with smtplib.SMTP(self.config.SMTP_SERVER, self.config.SMTP_PORT) as server:
                server.starttls()
                server.login(self.config.SMTP_USER, self.config.SMTP_PASSWORD)
                server.send_message(msg)
            logging.info(f"Log email successfully sent to {self.config.LOG_EMAIL_RECIPIENT}.")
        except Exception as e:
            logging.error(f"Failed to send log email: {e}", exc_info=True)

    def create_and_manage_kit_broadcast(self, email_subject_str, email_html_content_str, target_tag_id_int, description_str, send_at_utc_iso_str, preview_text_str):
        """Creates or schedules a broadcast in Kit with robust retry logic."""
        if not all([email_subject_str, email_html_content_str, self.config.KIT_API_KEY]):
            logging.error("Kit Broadcast Error: Missing subject, content, or API key.")
            return False, None, "CONFIG_ERROR"

        kit_payload = {
            "subject": email_subject_str, "content": email_html_content_str,
            "send_at": send_at_utc_iso_str, "description": description_str,
            "public": False, "preview_text": preview_text_str,
            "subscriber_filter": [{"all": [{"type": "tag", "ids": [target_tag_id_int]}]}]
        }
        kit_headers = {'Content-Type': 'application/json', 'X-Kit-Api-Key': self.config.KIT_API_KEY}

        try:
            action = "scheduling" if send_at_utc_iso_str else "creating draft for"
            logging.info(f"Attempting Kit V4 broadcast ({action}) for tag {target_tag_id_int}...")
            
            response = requests.post(self.config.KIT_BROADCAST_URL, headers=kit_headers, json=kit_payload, timeout=90)
            
            if response.status_code == 201:
                broadcast_id = response.json().get('broadcast', {}).get('id')
                return True, broadcast_id, response.status_code
            else:
                logging.warning(f"Kit V4 API Error (Tag {target_tag_id_int}) - Status {response.status_code}: {response.text[:400]}")
                return False, None, response.status_code

        except requests.exceptions.RequestException as e:
            logging.error(f"Kit V4 Broadcast API request failed for tag {target_tag_id_int}: {e}", exc_info=True)
            return False, None, "REQUEST_ERROR"

    def format_kit_email_html(self, articles_list, discipline_name=""):
        """Formats a list of articles into app-style content cards for the Kit email."""
        if not articles_list:
            return ""

        BRAND = "#0875C1"

        html_parts = [
            '<div style="background:#f8fafc;padding:20px 0;'
            'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;">'
        ]

        for i, article in enumerate(articles_list, start=1):
            title = (article.get('title') or 'N/A').strip()
            pmid = article.get('pubmed_id')
            url = article.get('pubmed_url') or (f"{CONFIG.PUBMED_BASE_URL}{pmid}/" if pmid else '#')
            summary = (article.get('llm_one_line_summary') or '').strip()
            show_summary = summary and "error" not in summary.lower() and "n/a" not in summary.lower()

            journal = (article.get('journal_iso_abbr') or article.get('journal') or '').strip()

            authors_raw = (article.get('authors_str') or article.get('authors') or '').strip().rstrip('.')
            pub_date = article.get('publication_date')
            year = pub_date.strftime("%Y") if isinstance(pub_date, date) else (article.get('pub_date_dict') or {}).get('Year', '')

            meta_parts = [p for p in [authors_raw, year] if p]
            meta_line = " · ".join(meta_parts)

            summary_html = (
                f'<p style="margin:0 0 20px;font-size:15px;color:#374151;line-height:1.65;">{summary}</p>'
            ) if show_summary else '<p style="margin:0 0 20px;"></p>'

            html_parts.append(
                # Card shell
                f'<div style="background:#ffffff;border-radius:10px;overflow:hidden;'
                f'margin:0 0 18px;border:1px solid #e2e8f0;max-width:600px;">'

                # Dark header: number box left, journal pill right
                f'<table width="100%" cellpadding="0" cellspacing="0" border="0">'
                f'<tr>'
                f'<td style="background:#0f172a;padding:12px 20px 12px;" valign="middle">'
                f'<span style="display:inline-block;background:#0c1a2e;border:1.5px solid {BRAND};'
                f'border-radius:8px;padding:6px 13px;font-size:22px;font-weight:800;color:{BRAND};'
                f'letter-spacing:-0.02em;line-height:1;">{i}</span>'
                f'</td>'
                f'<td style="background:#0f172a;padding:12px 20px 12px;" valign="middle" align="right">'
                f'<span style="display:inline-block;background:#1e293b;border:1px solid #334155;'
                f'border-radius:20px;padding:4px 12px;font-size:11px;color:#94a3b8;'
                f'text-transform:uppercase;letter-spacing:0.07em;font-weight:600;">{journal}</span>'
                f'</td>'
                f'</tr>'
                f'</table>'

                # White body
                f'<div style="padding:18px 20px 20px;">'
                f'<h3 style="margin:0 0 6px;font-size:19px;font-weight:700;line-height:1.3;color:#0f172a;">'
                f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
                f'style="color:#0f172a;text-decoration:none;">{title}</a>'
                f'</h3>'
                f'<p style="margin:0 0 16px;font-size:13px;color:#94a3b8;line-height:1.4;">{meta_line}</p>'
                f'{summary_html}'
                f'<div style="text-align:right;">'
                f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
                f'style="font-size:13px;font-weight:700;color:{BRAND};text-decoration:none;">'
                f'Read on PubMed &#8594;</a>'
                f'</div>'
                f'</div>'
                f'</div>'
            )

        html_parts.append('</div>')
        return "\n".join(html_parts)

class WorkflowManager:
    """Orchestrates the entire ETL and scheduling process."""
    def __init__(self, config, args):
        self.config = config
        self.args = args
        self.run_id = f"Run_{datetime.now():%Y%m%d_%H%M%S}"
        self.conn = None
        self.db_manager = None
        self.pubmed_fetcher = None
        self.article_filter = None
        self.llm_evaluator = None
        self.email_manager = None
        self.article_embedder = None
        self.overall_summary_stats = defaultdict(int)
        self.run_date_for_logic = date.today()
        if self.args.run_date:
            try:
                self.run_date_for_logic = datetime.strptime(self.args.run_date, "%Y-%m-%d").date()
                logging.warning(f"--- Overriding current date. Using '{self.run_date_for_logic}' for all date logic. ---")
            except ValueError:
                logging.error(f"Invalid --run-date format: '{self.args.run_date}'. Using today's date.")
        
        self.db_connection_url = self.config.DATABASE_URL # Start with the production URL

    def initialize(self):
        """Initializes all components and ensures DB tables exist."""
        
        # --- Test Database Safety Check ---
        if self.args.test_db_url:
            logging.critical("="*50)
            logging.critical("---      RUNNING IN TEST MODE      ---")
            logging.critical(f"--- Using Test Database: {self.args.test_db_url} ---")
            logging.critical("---     DRAFT-ONLY MODE IS FORCED   ---")
            logging.critical("="*50)
            self.args.draft_only = True # Force draft mode
            self.db_connection_url = self.args.test_db_url # Set the URL to the test one
        
        self.conn = get_db_connection(self.db_connection_url)
        if not self.conn: return False

        self.db_manager = DatabaseManager(self.conn)
        self.pubmed_fetcher = PubMedFetcher()
        self.article_filter = ArticleFilter(self.config)
        self.llm_evaluator = LLMEvaluator(self.config)
        self.email_manager = EmailManager(self.config)
        try:
            self.db_manager.create_tables()
            if self.config.ENABLE_SIMILARITY_PREFILTER and self.config.OLLAMA_BASE_URL:
                pgvector_ok = self.db_manager.setup_pgvector()
                if pgvector_ok:
                    self.article_embedder = ArticleEmbedder(
                        base_url=self.config.OLLAMA_BASE_URL,
                        api_key=self.config.OPENAI_API_KEY,
                        model_name=self.config.EMBEDDING_MODEL_NAME,
                        dimensions=self.config.EMBEDDING_DIMENSIONS,
                    )
                    logging.info(f"Similarity pre-filter enabled (model: {self.config.EMBEDDING_MODEL_NAME}, threshold: {self.config.SIMILARITY_LOW_THRESHOLD})")
            logging.info("Workflow components initialized successfully.")
            return True
        except Exception as e:
            logging.critical(f"Could not ensure database tables exist. Aborting. Error: {e}", exc_info=True)
            return False

    def _process_new_articles_for_discipline(self, query_config):
        """Complete workflow to get new, LLM-approved articles for one discipline."""
        discipline_name = query_config['discipline_name']
        discipline_id = query_config['id']
        search_term = query_config['query'] 
        heuristic = query_config['heuristic']
        logging.info(f"--- Processing new articles for {discipline_name} ---")

        fetched_articles = self.pubmed_fetcher.fetch_articles(search_term, discipline_name, run_date=self.run_date_for_logic)
        if not fetched_articles:
            logging.warning(f"No new articles found on PubMed for {discipline_name}.")
            return []

        # --- NEW DISCIPLINE-SPECIFIC DUPLICATION CHECK ---
        all_fetched_pmids = [art['pubmed_id'] for art in fetched_articles]
        # Check against 'article_evaluations' table for this discipline_id
        processed_pmids = self.db_manager.get_processed_pmids_for_discipline(discipline_id, all_fetched_pmids)
        
        if processed_pmids:
            logging.info(f"Pre-screening identified {len(processed_pmids)} PMIDs that have already been processed for '{discipline_name}'. Filtering them out.")
            articles_to_process = [art for art in fetched_articles if art['pubmed_id'] not in processed_pmids]
        else:
            articles_to_process = fetched_articles
        
        if not articles_to_process:
            logging.warning(f"All fetched articles for '{discipline_name}' were duplicates or already processed. Nothing new to evaluate.")
            return []
        # --- END NEW DUPLICATION CHECK ---

        prefiltered = self.article_filter.filter_articles(articles_to_process, discipline_name)

        # --- Cosine similarity pre-filter ---
        embedding_map: dict[int, list[float]] = {}
        articles_for_llm = prefiltered
        auto_no_articles: list[dict] = []

        if self.article_embedder and prefiltered:
            articles_with_embeddings: list[tuple[dict, list[float] | None]] = []
            with ThreadPoolExecutor(max_workers=self.config.MAX_LLM_CONCURRENT_REQUESTS) as executor:
                future_to_article = {
                    executor.submit(self.article_embedder.embed_article, art): art
                    for art in prefiltered
                }
                for future in as_completed(future_to_article):
                    art = future_to_article[future]
                    try:
                        emb = future.result()
                        articles_with_embeddings.append((art, emb))
                        if emb:
                            embedding_map[art['pubmed_id']] = emb
                    except Exception as e:
                        logging.warning(f"Embedding failed for PMID {art.get('pubmed_id')}: {e}")
                        articles_with_embeddings.append((art, None))

            yes_corpus = self.db_manager.fetch_yes_corpus_embeddings(discipline_id)
            if yes_corpus:
                articles_for_llm, auto_no_articles = self.article_embedder.partition_by_similarity(
                    articles_with_embeddings, yes_corpus, self.config.SIMILARITY_LOW_THRESHOLD
                )
                logging.info(
                    f"Similarity filter for '{discipline_name}': "
                    f"{len(articles_for_llm)} → LLM, {len(auto_no_articles)} auto-rejected "
                    f"(corpus: {len(yes_corpus)} Yes articles, threshold: {self.config.SIMILARITY_LOW_THRESHOLD})"
                )
                for article in auto_no_articles:
                    article_id = self.db_manager.upsert_article(article)
                    if article_id:
                        score = article.get('_similarity_score', 0.0)
                        self.db_manager.upsert_evaluation(article_id, discipline_id, {
                            'decision': 'No',
                            'summary_text': 'N/A',
                            'initial_rationale_text': f'Auto-rejected: similarity {score:.3f} < threshold {self.config.SIMILARITY_LOW_THRESHOLD}',
                        })
                        emb = embedding_map.get(article['pubmed_id'])
                        if emb:
                            self.db_manager.upsert_article_embedding(article_id, emb)
            else:
                logging.info(f"No Yes corpus yet for '{discipline_name}' — sending all {len(prefiltered)} articles to LLM.")
                articles_for_llm = prefiltered

        # --- LLM evaluation ---
        yes_articles = []
        with ThreadPoolExecutor(max_workers=self.config.MAX_LLM_CONCURRENT_REQUESTS) as executor:
            future_to_article = {
                executor.submit(self.llm_evaluator.get_initial_decision_and_summary, article, heuristic, discipline_name): article
                for article in articles_for_llm
            }
            for future in as_completed(future_to_article):
                article = future_to_article[future]
                try:
                    eval_result = future.result()
                    article_id = self.db_manager.upsert_article(article)
                    if article_id:
                        eval_id = self.db_manager.upsert_evaluation(article_id, discipline_id, eval_result)
                        emb = embedding_map.get(article['pubmed_id'])
                        if emb:
                            self.db_manager.upsert_article_embedding(article_id, emb)
                        if eval_id and eval_result['decision'] == 'Yes':
                            yes_article_data = article.copy()
                            yes_article_data['llm_one_line_summary'] = eval_result.get('summary_text')
                            yes_article_data['eval_id'] = eval_id
                            yes_articles.append(yes_article_data)
                except Exception as exc:
                    logging.error(f"PMID {article.get('pubmed_id')} generated an exception during processing: {exc}", exc_info=True)
        
        logging.info(f"Found {len(yes_articles)} new 'Yes' articles for {discipline_name}.")
        return yes_articles

    def _get_weekdays_in_month(self, year, month, start_day):
        """Calculates the number of weekdays from start_day to the end of the month."""
        num_days_in_month = monthrange(year, month)[1]
        weekdays = 0
        for day in range(start_day, num_days_in_month + 1):
            if date(year, month, day).weekday() < 5: # 0-4 are Mon-Fri
                weekdays += 1
        return weekdays

    def _schedule_daily_kit_emails_monthly(self, daily_batches, discipline_config, schedule_start_date, initial_monday_utc_time):
        """
        NEW: Batches and schedules the final list of articles across all
        remaining weekdays in the month.
        """
        discipline_name = discipline_config.get('discipline_name')
        ck_tag_id = discipline_config.get('convertkit_tag_id')

        if not ck_tag_id:
            logging.warning(f"No ConvertKit Tag ID for {discipline_name}. Skipping email scheduling.")
            return initial_monday_utc_time

        current_monday_send_time = initial_monday_utc_time
        current_schedule_date = schedule_start_date
        
        for day_idx, daily_batch in enumerate(daily_batches):
            if not daily_batch: continue

            # Find the next valid weekday for this batch
            while current_schedule_date.weekday() >= 5: # Skip Sat (5) and Sun (6)
                current_schedule_date += timedelta(days=1)
            
            target_date = current_schedule_date
            subject = f"{discipline_name} JournalFeed - Speed Read - {target_date:%A}"
            html_content = self.email_manager.format_kit_email_html(daily_batch, discipline_name=discipline_name)

            if not html_content:
                logging.error(f"HTML content empty for {discipline_name} on {target_date:%A}. Skipping.")
                current_schedule_date += timedelta(days=1) # Move to next day
                continue

            # Calculate send time, allowing for drafts
            send_time_iso = None
            if not self.args.draft_only and ZoneInfo and current_monday_send_time:
                try:
                    local_tz = ZoneInfo(self.config.KIT_SCHEDULE_TIMEZONE_STR)
                    # Get the *time* from the base send time
                    base_local_time = current_monday_send_time.astimezone(local_tz).time()
                    # Combine the *target date* with the *base time*
                    target_local_dt = datetime.combine(target_date, base_local_time, tzinfo=local_tz)
                    send_time_iso = target_local_dt.astimezone(timezone.utc).isoformat()
                except Exception as e:
                    logging.error(f"Error calculating send time for {target_date:%A}: {e}. Will create draft.")
            
            # API call with retry logic for time conflicts (422)
            max_retries, attempt, success = 3, 0, False
            while not success and attempt < max_retries:
                attempt += 1
                success, _, status_code = self.email_manager.create_and_manage_kit_broadcast(
                    email_subject_str=subject, email_html_content_str=html_content,
                    target_tag_id_int=int(ck_tag_id), description_str=f"Digest for {discipline_name}, content for {target_date:%A}",
                    send_at_utc_iso_str=send_time_iso, preview_text_str="You're up to Speed!"
                )
                if success: break
                
                if status_code == 422 and send_time_iso:
                    # Time conflict, adjust and retry
                    logging.warning(f"Kit API 422 (Time Conflict). Adjusting time by 10 mins.")
                    new_time = datetime.fromisoformat(send_time_iso) + timedelta(minutes=10)
                    send_time_iso = new_time.isoformat()
                    if day_idx == 0: current_monday_send_time = new_time # Persist adjustment for next disciplines
                    SCRIPT_TIME_MODULE.sleep(5)
                elif status_code == 429: # Rate limit
                    backoff = (2 ** attempt) * 2
                    logging.warning(f"Kit API 429 (Rate Limit). Backing off for {backoff}s.")
                    SCRIPT_TIME_MODULE.sleep(backoff)
                else: break # Unrecoverable error

            if success:
                status_suffix = target_date.strftime("%Y%m%d")
                status_msg = f'kit_scheduled_{status_suffix}' if send_time_iso else f'kit_drafted_{status_suffix}'
                eval_ids_to_update = [art['eval_id'] for art in daily_batch if 'eval_id' in art]
                self.db_manager.update_evaluation_status_bulk(eval_ids_to_update, status_msg)
                self.overall_summary_stats[f"{discipline_name}_kit_emails_processed"] += 1
            else:
                logging.error(f"Failed to schedule Kit email for {discipline_name} on {target_date:%A} after retries.")
                self.overall_summary_stats[f"{discipline_name}_kit_email_failures"] += 1
            
            # Increment date for the *next* batch
            current_schedule_date += timedelta(days=1)
            SCRIPT_TIME_MODULE.sleep(2) # Be polite to the Kit API

        return current_monday_send_time

    def _distribute_articles_into_daily_batches(self, articles, num_days):
        """Distributes a list of articles evenly across a number of days."""
        if not articles or num_days <= 0: return [[] for _ in range(num_days)]
        # Sort to make batches deterministic
        articles.sort(key=lambda x: x.get('pubmed_id', 0))
        base_size = len(articles) // num_days
        remainder = len(articles) % num_days
        batches, start_idx = [], 0
        for i in range(num_days):
            end_idx = start_idx + base_size + (1 if i < remainder else 0)
            batches.append(articles[start_idx:end_idx])
            start_idx = end_idx
        return batches
    
    # --- ADD TO CLASS WorkflowManager ---

    def _heal_missing_summaries(self, articles, heuristic, discipline_name):
        """
        Scans articles for missing summaries (caused by previous script bugs).
        Regenerates them using the LLM and updates the DB.
        """
        # Filter for articles where summary is None, empty, or "N/A"
        articles_needing_healing = [
            a for a in articles 
            if not a.get('llm_one_line_summary') or a.get('llm_one_line_summary') == 'N/A'
        ]
        
        if not articles_needing_healing:
            return articles # All good!

        logging.warning(f"--- HEALING REQUIRED: Found {len(articles_needing_healing)} 'Yes' articles with missing summaries for {discipline_name}. Regenerating... ---")
        
        system_prompt = "You are a medical editor. Create a single-sentence summary."
        
        for article in articles_needing_healing:
            pmid = article.get('pubmed_id')
            user_prompt = (
                f"Write a one-sentence summary for this {discipline_name} article (Population, Intervention, Outcome).\n\n"
                f"Title: {article.get('title')}\nAbstract: {article.get('abstract')}\n\n"
                f"Output ONLY the summary text."
            )
            
            # Call LLM directly (small token limit for summary)
            summary_text = self.llm_evaluator._call_llm_api(pmid, user_prompt, system_prompt, 200)
            
            if summary_text and "LLM Error" not in summary_text:
                clean_summary = summary_text.replace('"', '').strip()
                # 1. Update DB so we don't have to do this next time
                self.db_manager.update_evaluation_summary(article['eval_id'], clean_summary)
                # 2. Update the local dictionary so the email sends correctly NOW
                article['llm_one_line_summary'] = clean_summary
                logging.info(f"Healed summary for PMID {pmid}")
            else:
                logging.error(f"Failed to heal summary for PMID {pmid}")
                
        return articles
    
    def _execute_db_only_mode(self):
        """ REFACTORED: Simple "process all pending" mode. """
        logging.info("--- Operating in DB-Only Mode ---")
        active_queries = self.db_manager.fetch_active_queries(target_discipline_name=self.args.discipline)
        if not active_queries:
            logging.warning("DB-Only Mode: No active queries found.")
            return

        # --- Set up scheduling parameters for the month ---
        today = self.run_date_for_logic
        
        # Find the next business day to start scheduling
        schedule_start_date = today
        if schedule_start_date.weekday() >= 5: # If today is Sat/Sun
            days_to_monday = 7 - schedule_start_date.weekday()
            schedule_start_date += timedelta(days=days_to_monday)
        
        num_days_to_fill = self._get_weekdays_in_month(
            schedule_start_date.year, 
            schedule_start_date.month, 
            schedule_start_date.day
        )
        if num_days_to_fill == 0:
            logging.warning("DB-Only: No weekdays left in the month to schedule. Exiting.")
            return

        logging.info(f"DB-Only: Scheduling emails to fill {num_days_to_fill} weekdays, starting {schedule_start_date:%Y-%m-%d}")

        # Calculate the initial send time
        next_available_send_time = None
        if ZoneInfo:
            try:
                local_tz = ZoneInfo(self.config.KIT_SCHEDULE_TIMEZONE_STR)
                local_start_time = time(self.config.KIT_SCHEDULE_LOCAL_HOUR_START, self.config.KIT_SCHEDULE_LOCAL_MINUTE_START)
                # Base the time on the *first* available schedule date
                next_available_send_time = datetime.combine(schedule_start_date, local_start_time, tzinfo=local_tz).astimezone(timezone.utc)
            except Exception as e:
                logging.error(f"Error initializing base scheduling time: {e}. All emails will be created as drafts.")

        for query_config in active_queries:
            discipline_name = query_config['discipline_name']
            logging.info(f"===== Processing Discipline from DB: {discipline_name} =====")
            
            # Fetch ALL 'Yes'/'pending' articles from the DB for this discipline
            articles_for_scheduling = self.db_manager.fetch_articles_for_kit_email([discipline_name])
            logging.info(f"DB-Only: Found {len(articles_for_scheduling)} 'pending' articles in DB for '{discipline_name}'.")

            if len(articles_for_scheduling) < self.config.MIN_ARTICLES_FOR_KIT_EMAIL:
                logging.warning(f"Final count for {discipline_name} ({len(articles_for_scheduling)}) is below minimum. Skipping scheduling.")
                continue
            
            logging.info(f"Final curated list for {discipline_name} contains {len(articles_for_scheduling)} articles for this month.")

            # Distribute these articles across the remaining weekdays
            daily_batches = self._distribute_articles_into_daily_batches(articles_for_scheduling, num_days_to_fill)
            
            # Schedule the emails
            adjusted_time = self._schedule_daily_kit_emails_monthly(
                daily_batches, query_config, schedule_start_date, next_available_send_time
            )
            if adjusted_time:
                # Increment the start time for the next discipline to avoid conflicts
                next_available_send_time = adjusted_time + timedelta(minutes=5)

    def execute(self):
        """
        Main execution method.
        REFACTORED to a "one-pass" system for resilience.
        It processes and schedules one discipline completely before starting the next.
        """
        logging.info(f"===== Script Execution Started (Run ID: {self.run_id}) =====")
        start_time = SCRIPT_TIME_MODULE.time()
        send_alert(
            f"Pipeline started (Run {self.run_id})",
            f"headless_app.py started.\nRun ID: {self.run_id}\nDate: {self.run_date_for_logic}",
            level="INFO",
        )

        try:
            # --- Check if today is the configured day of the month ---
            if not (self.run_date_for_logic.day == self.config.PUBMED_FETCH_DAY_OF_MONTH or self.args.force_run):
                logging.info(f"Today is not the {self.config.PUBMED_FETCH_DAY_OF_MONTH}nd/rd/th of the month and --force_run is not set. Exiting.")
                return

            active_queries = self.db_manager.fetch_active_queries(target_discipline_name=self.args.discipline)
            if not active_queries:
                logging.warning("No active disciplines found in the database. Nothing to process.")
                return

            # --- Set up scheduling parameters for the month ---
            today = self.run_date_for_logic
            
            # Find the next business day to start scheduling
            schedule_start_date = today
            if schedule_start_date.weekday() >= 5: # If today is Sat/Sun
                days_to_monday = 7 - schedule_start_date.weekday()
                schedule_start_date += timedelta(days=days_to_monday)
            
            num_days_to_fill = self._get_weekdays_in_month(
                schedule_start_date.year, 
                schedule_start_date.month, 
                schedule_start_date.day
            )
            if num_days_to_fill == 0:
                logging.warning("No weekdays left in the month to schedule. Exiting scheduling phase.")
                return

            logging.info(f"--- Scheduling Phase ---")
            logging.info(f"Will distribute articles over {num_days_to_fill} weekdays, starting {schedule_start_date:%Y-%m-%d}")
            
            next_available_send_time = None
            if ZoneInfo:
                try:
                    local_tz = ZoneInfo(self.config.KIT_SCHEDULE_TIMEZONE_STR)
                    local_start_time = time(self.config.KIT_SCHEDULE_LOCAL_HOUR_START, self.config.KIT_SCHEDULE_LOCAL_MINUTE_START)
                    next_available_send_time = datetime.combine(schedule_start_date, local_start_time, tzinfo=local_tz).astimezone(timezone.utc)
                except Exception as e:
                    logging.error(f"Error initializing base scheduling time: {e}. All emails will be created as drafts.")

            for query_config in active_queries:
                discipline_name = query_config['discipline_name']
                logging.info(f"========== Processing Discipline: {discipline_name} ==========")
                try:
                    # Step 1: Process NEW articles (Upsert into DB)
                    _ = self._process_new_articles_for_discipline(query_config)

                    # Calculate the date range for the previous full month
                    first_of_this_month = self.run_date_for_logic.replace(day=1)
                    end_date_val = first_of_this_month - timedelta(days=1)
                    start_date_val = end_date_val.replace(day=1)

                    logging.info(f"Retrieving ALL approved articles for {discipline_name} from {start_date_val} to {end_date_val}...")

                    final_articles_for_scheduling = self.db_manager.fetch_approved_articles_by_date_range(
                        query_config['id'],
                        start_date_val,
                        end_date_val
                    )

                    final_articles_for_scheduling = self._heal_missing_summaries(
                        final_articles_for_scheduling,
                        query_config['heuristic'],
                        discipline_name
                    )

                    # Step 2: Check if we have enough articles to send for the *whole month*
                    if len(final_articles_for_scheduling) < self.config.MIN_ARTICLES_FOR_KIT_EMAIL:
                        logging.warning(f"Final article count for {discipline_name} ({len(final_articles_for_scheduling)}) is below monthly minimum of {self.config.MIN_ARTICLES_FOR_KIT_EMAIL}. Skipping email scheduling.")
                        continue

                    # Step 3: Check if we've exceeded the max
                    if len(final_articles_for_scheduling) > self.config.MAX_ARTICLES_FOR_KIT_EMAIL:
                        logging.warning(f"Article count for {discipline_name} ({len(final_articles_for_scheduling)}) exceeds max of {self.config.MAX_ARTICLES_FOR_KIT_EMAIL}. Culling to best.")
                        final_articles_for_scheduling = self.llm_evaluator.select_best_articles(
                            final_articles_for_scheduling,
                            discipline_name,
                            self.config.MAX_ARTICLES_FOR_KIT_EMAIL
                        )

                    logging.info(f"Final curated list for {discipline_name} contains {len(final_articles_for_scheduling)} articles for this month.")

                    # Step 4: Distribute these articles across the remaining weekdays
                    daily_batches = self._distribute_articles_into_daily_batches(final_articles_for_scheduling, num_days_to_fill)

                    # Step 5: Schedule the daily emails in Kit
                    adjusted_time = self._schedule_daily_kit_emails_monthly(
                        daily_batches, query_config, schedule_start_date, next_available_send_time
                    )
                    if adjusted_time:
                        next_available_send_time = adjusted_time + timedelta(minutes=5)

                except Exception as e_disc:
                    logging.critical(f"Discipline '{discipline_name}' failed with an unhandled exception: {e_disc}", exc_info=True)
                    send_alert(
                        f"Discipline FAILED: {discipline_name}",
                        f"Run ID: {self.run_id}\nDiscipline: {discipline_name}\n\n{traceback.format_exc()}",
                    )

        except SystemExit as e:
            logging.info(f"Script exited via SystemExit: {e}")
        except Exception as e_critical:
            logging.critical(f"A critical unhandled exception occurred in the main workflow: {e_critical}", exc_info=True)
        finally:
            end_time = SCRIPT_TIME_MODULE.time()
            total_duration = end_time - start_time
            
            logging.info(f"--- Run Summary (ID: {self.run_id}) ---")
            logging.info(f"Total script execution time: {total_duration:.2f} seconds.")
            if self.llm_evaluator: logging.info(f"LLM Stats: {self.llm_evaluator.get_llm_stats()}")

            if self.email_manager:
                if string_io_handler: string_io_handler.flush()
                log_contents = log_capture_string.getvalue()
                self.email_manager.send_log_email(self.run_id, log_contents)

            if self.conn: self.conn.close(); logging.info("Database connection closed.")
            logging.info(f"===== Script Execution Finished (Run ID: {self.run_id}) =====")
            log_capture_string.truncate(0)
            log_capture_string.seek(0)

def main():
    """Main entry point: sets up logging, parses arguments, and executes the workflow."""
    # Create a uniquely named log file for each run
    base_log_path = CONFIG.LOG_FILE_PATH
    log_dir = os.path.dirname(base_log_path)
    base_filename, extension = os.path.splitext(os.path.basename(base_log_path))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{base_filename}_{timestamp}{extension}"
    full_log_path = os.path.join(log_dir, log_filename)
    setup_logging(full_log_path)

    parser = argparse.ArgumentParser(
        description="Headless ETL script to fetch, filter, and schedule PubMed article digests.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--discipline", type=str, default=None, help="Run for ONE specific discipline name from the database.")
    parser.add_argument("--force-run", action="store_true", help="Force main monthly logic to run, even if it is not the 2nd of the month.")
    parser.add_argument("--run-date", type=str, default=None, help="Simulate running on a specific date (YYYY-MM-DD) for reproducible results.")
    parser.add_argument("--draft-only", action="store_true", help="Create all broadcasts as drafts in ConvertKit, without scheduling them to be sent.")
    parser.add_argument("--use-db-articles-only-for-emailing", action="store_true", help="Skip PubMed fetching and process existing 'pending' articles from DB.")
    parser.add_argument("--test-db-url", type=str, default=None, help="TESTING: Connection string for a test database. FORCES --draft-only.")
    args = parser.parse_args()

    # --- Pre-run Environment Checks ---
    if not CONFIG.DATABASE_URL and not args.test_db_url:
        logging.critical("FATAL_ENV_PRECHECK: DATABASE_URL is not set and --test-db-url is not provided. Exiting."); sys.exit(1)
    if not (CONFIG.OLLAMA_BASE_URL or os.getenv("OPENAI_API_KEY")):
        logging.critical("FATAL_ENV_PRECHECK: No LLM endpoint configured (OLLAMA_BASE_URL or OPENAI_API_KEY). Exiting."); sys.exit(1)
    # ADDED: Fail-fast check for the Kit API key if we're not in a test/draft mode
    if not CONFIG.KIT_API_KEY and not args.draft_only and not args.test_db_url:
        logging.critical("FATAL_ENV_PRECHECK: KIT_API_KEY is not set. Cannot schedule emails. Exiting."); sys.exit(1)


    # --- Execute Workflow ---
    main_workflow = WorkflowManager(CONFIG, args)
    try:
        # Initialization must happen first to handle test-db-url logic
        if not main_workflow.initialize():
            logging.critical("FATAL: Workflow initialization failed. Exiting.")
            send_alert("Pipeline FAILED to initialize", "headless_app.py could not initialize (DB, LLM endpoint, or config). No disciplines were processed.")
            sys.exit(1)

        if main_workflow.args.use_db_articles_only_for_emailing:
            main_workflow._execute_db_only_mode()
        else:
            main_workflow.execute()
    except Exception as e:
        run_id = getattr(main_workflow, 'run_id', 'UNKNOWN_RUN')
        logging.critical(f"Unhandled TOP-LEVEL exception in main execution block (Run ID: {run_id}): {e}", exc_info=True)
        send_alert(f"Pipeline CRASHED (Run {run_id})", f"Unhandled top-level exception.\n\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()