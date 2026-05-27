import logging
import math
from openai import OpenAI

from .config import CONFIG


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _max_similarity(candidate: list[float], corpus: list[list[float]]) -> float:
    if not corpus:
        return 0.0
    return max(_cosine_similarity(candidate, ref) for ref in corpus)


class ArticleEmbedder:
    def __init__(self):
        self.client = OpenAI(
            base_url=CONFIG.LLM_BASE_URL,
            api_key=CONFIG.LLM_API_KEY,
        )
        self.model = CONFIG.LLM_EMBEDDING_MODEL

    def embed_text(self, text: str) -> list[float] | None:
        """Embeds a single string. Returns None on failure."""
        if not text or not text.strip():
            return None
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text[:8000],  # guard against very long texts
            )
            return response.data[0].embedding
        except Exception as e:
            logging.warning(f"Embedding failed: {e}")
            return None

    def embed_article(self, article: dict) -> list[float] | None:
        """Embeds title + first 500 chars of body as the article's vector."""
        title = article.get('title', '')
        body  = (article.get('full_text') or '')[:500]
        return self.embed_text(f"{title}\n\n{body}")

    def embed_teacher_profile(self, teacher: dict) -> list[float] | None:
        """Embeds the teacher's discipline + current module + tailoring query."""
        parts = [
            teacher.get('discipline', ''),
            teacher.get('current_module', ''),
            teacher.get('tailoring_query', ''),
        ]
        text = ' | '.join(p for p in parts if p)
        return self.embed_text(text)

    def partition_by_similarity(
        self,
        articles_with_embeddings: list[tuple[dict, list[float] | None]],
        teacher_embedding: list[float],
        yes_corpus: list[list[float]],
        threshold: float,
    ) -> tuple[list[dict], list[dict]]:
        """
        Splits articles into (send_to_llm, auto_reject) based on cosine similarity.

        Strategy:
        - If a Yes-corpus exists, score against corpus AND teacher profile,
          take the max. Articles below threshold are auto-rejected.
        - If no corpus yet, use teacher-profile similarity only.
        """
        for_llm, auto_no = [], []

        for article, emb in articles_with_embeddings:
            if emb is None:
                # Can't score — send to LLM anyway, don't discard
                for_llm.append(article)
                continue

            scores = [_cosine_similarity(emb, teacher_embedding)]
            if yes_corpus:
                scores.append(_max_similarity(emb, yes_corpus))

            best_score = max(scores)
            article['_similarity_score'] = best_score

            if best_score >= threshold:
                for_llm.append(article)
            else:
                auto_no.append(article)

        return for_llm, auto_no
