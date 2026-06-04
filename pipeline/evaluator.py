import json
import logging
import re
import threading
import time

import requests
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from .config import CONFIG


class _EndpointPool:
    """Thread-safe round-robin pool of LLM endpoints with per-endpoint OpenAI clients."""

    def __init__(self, endpoints: list[str], api_key: str):
        self._endpoints = endpoints
        self._clients = [OpenAI(base_url=ep, api_key=api_key) for ep in endpoints]
        self._idx = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._endpoints)

    def next(self) -> tuple[str, "OpenAI"]:
        with self._lock:
            i = self._idx
            self._idx = (self._idx + 1) % len(self._endpoints)
        return self._endpoints[i], self._clients[i]


def _call_native_lmstudio(model: str, system_prompt: str, user_prompt: str, native_url: str) -> str:
    """
    Calls LM Studio's native /api/v1/chat endpoint.
    Handles thinking/reasoning models (Gemma 4, etc.) by extracting only the
    'message' type output, ignoring 'reasoning' content.
    """
    payload = {
        "model": model,
        "system_prompt": system_prompt,
        "input": user_prompt,
    }
    resp = requests.post(native_url, json=payload, timeout=600)
    resp.raise_for_status()
    data = resp.json()

    # Extract the final message (not the reasoning chain)
    for item in data.get("output", []):
        if item.get("type") == "message":
            return item.get("content", "").strip()

    # Fallback: return everything if no message type found
    return json.dumps(data.get("output", ""))


# ------------------------------------------------------------------
# Output contract validation
# ------------------------------------------------------------------

class ArticleEvaluation(BaseModel):
    decision: str = Field(..., pattern=r"^(Yes|No)$")
    summary: str = ""
    action_steps: list[str] = Field(default_factory=list)
    mission_alignment: str = ""
    reason: str = ""

    @field_validator('summary', 'mission_alignment', 'reason', mode='before')
    @classmethod
    def coerce_none_to_str(cls, v):
        return v or ""

    @field_validator('action_steps', mode='before')
    @classmethod
    def coerce_steps(cls, v):
        if v is None:
            return []
        return [s.strip() for s in v if s and str(s).strip()]


# ------------------------------------------------------------------
# LLM Evaluator
# ------------------------------------------------------------------

from .prompts import get_system_prompt, get_search_keyword_prompt

class LLMEvaluator:
    def __init__(self):
        self.pool = _EndpointPool(CONFIG.LLM_ENDPOINTS, CONFIG.LLM_API_KEY)
        self.total_prompt_tokens     = 0
        self.total_completion_tokens = 0
        logging.info(f"LLMEvaluator: {len(self.pool)} endpoint(s): {CONFIG.LLM_ENDPOINTS}")

    def _call(self, label: str, user_prompt: str, system_prompt: str, max_tokens: int = 1024) -> str:
        # Native API path (single endpoint — no round-robin for native calls)
        if CONFIG.LLM_NATIVE_API_URL:
            for attempt in range(CONFIG.LLM_RETRY_ATTEMPTS + 1):
                try:
                    return _call_native_lmstudio(
                        CONFIG.LLM_MODEL_NAME, system_prompt, user_prompt, CONFIG.LLM_NATIVE_API_URL
                    )
                except Exception as e:
                    last_error = str(e)
                    if attempt < CONFIG.LLM_RETRY_ATTEMPTS:
                        logging.warning(f"[{label}] Native LLM failed ({last_error}). Retrying...")
                        time.sleep(CONFIG.LLM_RETRY_DELAY_SECONDS)
            logging.error(f"[{label}] Native LLM failed definitively: {last_error}")
            return f"LLM Error - {last_error}"

        # Round-robin across endpoints: try each once per round, retry up to LLM_RETRY_ATTEMPTS rounds
        n = len(self.pool)
        last_error = "Unknown"
        for round_num in range(CONFIG.LLM_RETRY_ATTEMPTS + 1):
            if round_num > 0:
                logging.warning(f"[{label}] All {n} endpoint(s) failed. Waiting before retry round {round_num}...")
                time.sleep(CONFIG.LLM_RETRY_DELAY_SECONDS * round_num)
            for _ in range(n):
                endpoint_url, client = self.pool.next()
                try:
                    resp = client.chat.completions.create(
                        model=CONFIG.LLM_MODEL_NAME,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user",   "content": user_prompt},
                        ],
                        max_tokens=max_tokens,
                        temperature=0.2,
                    )
                    if resp.usage:
                        self.total_prompt_tokens     += resp.usage.prompt_tokens
                        self.total_completion_tokens += resp.usage.completion_tokens
                    return resp.choices[0].message.content.strip()
                except Exception as e:
                    last_error = str(e)
                    logging.warning(f"[{label}] Endpoint {endpoint_url} failed ({last_error}). Trying next...")

        logging.error(f"[{label}] LLM failed definitively across all endpoints: {last_error}")
        return f"LLM Error - {last_error}"

    def generate_keywords(self, teacher: dict) -> list[str]:
        """
        Generates search keywords for a teacher profile.
        """
        label = f"keywords|{teacher['email']}"
        system_prompt = "You are a helpful educational research librarian."
        user_prompt = get_search_keyword_prompt(teacher)
        
        raw = self._call(label, user_prompt, system_prompt, max_tokens=256)
        if raw.startswith("LLM Error"):
            return []
            
        keywords = [k.strip() for k in raw.split(',') if k.strip()]
        logging.info(f"  Keywords for {teacher['email']}: {keywords}")
        return keywords

    def evaluate(self, article: dict, teacher: dict, rated_titles: dict | None = None) -> dict:
        """
        Evaluates one article against one teacher profile.
        Returns a dict matching the ArticleEvaluation schema plus a raw 'decision' key.
        """
        label = f"{article.get('source_id','?')[:8]}|{teacher['email']}"

        system_prompt = get_system_prompt(teacher, rated_titles)

        user_prompt = (
            f"Evaluate the following article for THIS teacher.\n\n"
            f"**Article:**\n"
            f"- Title: {article.get('title', 'N/A')}\n"
            f"- Source: {article.get('source', 'N/A')}\n"
            f"- Text: {(article.get('full_text') or '')[:2000]}\n\n"
            f"**Instructions:**\n"
            f"1. Decide if this article is relevant to the teacher's profile (Yes/No).\n"
            f"2. If Yes, provide summary, action_steps, and mission_alignment as requested in the system prompt.\n"
            f"3. If No, set summary/action_steps/mission_alignment to brief rejection reasons.\n\n"
            f"Respond with ONLY the JSON object."
        )

        raw = self._call(label, user_prompt, system_prompt, max_tokens=1024)

        if raw.startswith("LLM Error"):
            return {"decision": "Error", "summary": raw, "action_steps": [], "mission_alignment": ""}

        try:
            cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw, flags=re.DOTALL).strip()
            parsed = json.loads(cleaned)

            # Normalize the No case — LLM may return {"decision":"No","reason":"..."}
            if parsed.get("decision") == "No":
                reason = parsed.get("reason") or parsed.get("summary") or "Not relevant to this teacher's context."
                return {"decision": "No", "summary": reason, "action_steps": [], "mission_alignment": ""}

            validated = ArticleEvaluation.model_validate(parsed)
            return validated.model_dump()
        except Exception as e:
            logging.warning(f"[{label}] JSON parse failed ({e}). Raw: {raw[:300]}")
            return {"decision": "Error", "summary": f"Parse error: {e}", "action_steps": [], "mission_alignment": ""}

    def get_stats(self) -> dict:
        return {
            "prompt_tokens":     self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens":      self.total_prompt_tokens + self.total_completion_tokens,
        }
