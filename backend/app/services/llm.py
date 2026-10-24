import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import List, Dict, Any, Optional
import torch
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.config import settings

logger = logging.getLogger(__name__)

# Global singletons
_embedding_model = None
_tokenizer = None
_genai_client = None

# BGE retrieval query instruction
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

DAILY_QUOTA_ERROR_MESSAGE = "Daily Gemini quota reached, resets around 12:30 PM IST"


class GeminiDailyQuotaError(Exception):
    """Raised when Gemini daily quota is reached. Non-retryable."""
    def __init__(self, message: str = DAILY_QUOTA_ERROR_MESSAGE):
        super().__init__(message)


def is_daily_quota_error(exc: BaseException) -> bool:
    """Check if exception represents a non-retryable daily quota exhaustion."""
    if isinstance(exc, GeminiDailyQuotaError):
        return True
    msg = str(exc).lower()
    is_429 = "429" in msg or "resource_exhausted" in msg or "resourceexhausted" in msg
    daily_keywords = [
        "per day",
        "perday",
        "daily",
        "requests per day",
        "requestsperday",
        "generatecontentrequestsperday",
        "generatecontentrequestsperdayperprojectperregion",
        "free tier limit: 0",
        "daily quota",
    ]
    return is_429 and any(kw in msg for kw in daily_keywords)


def is_retryable_llm_error(exc: BaseException) -> bool:
    """
    Check if exception is a retryable rate limit (per-minute 429) or transient server error.
    Daily quota errors MUST NOT be retried.
    """
    if is_daily_quota_error(exc):
        return False
    msg = str(exc).lower()
    return any(err in msg for err in ["429", "resource_exhausted", "503", "unavailable", "500", "internal"])


class LLMUsageTracker:
    """Thread-safe usage tracker for counting Gemini calls and tokens per paper or session."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.calls: int = 0
            self.prompt_tokens: int = 0
            self.completion_tokens: int = 0
            self.total_tokens: int = 0
            self.cache_hits: int = 0

    def record_call(self, prompt_tokens: int, completion_tokens: int, total_tokens: Optional[int] = None):
        with self._lock:
            self.calls += 1
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.total_tokens += total_tokens if total_tokens is not None else (prompt_tokens + completion_tokens)

    def record_cache_hit(self):
        with self._lock:
            self.cache_hits += 1

    def to_dict(self) -> Dict[str, int]:
        with self._lock:
            return {
                "calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
                "cache_hits": self.cache_hits,
            }

    def summary_string(self) -> str:
        with self._lock:
            return (
                f"Gemini API: {self.calls} calls ({self.cache_hits} cache hits) | "
                f"{self.prompt_tokens:,} prompt tokens | "
                f"{self.completion_tokens:,} completion tokens | "
                f"{self.total_tokens:,} total tokens"
            )


_usage_tracker = LLMUsageTracker()


def get_llm_tracker() -> LLMUsageTracker:
    return _usage_tracker


def reset_llm_stats():
    _usage_tracker.reset()


def get_llm_stats() -> Dict[str, int]:
    return _usage_tracker.to_dict()


def get_llm_usage_summary() -> str:
    return _usage_tracker.summary_string()


class LLMCache:
    """Thread-safe persistent cache for identical LLM generation prompts."""

    def __init__(self, db_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._memory_cache: Dict[str, str] = {}
        if db_path is None:
            cache_dir = Path(__file__).resolve().parent.parent.parent / ".cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = cache_dir / "llm_cache.db"
        else:
            self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prompt_cache (
                        cache_key TEXT PRIMARY KEY,
                        response_json TEXT NOT NULL,
                        model TEXT,
                        prompt_tokens INTEGER,
                        completion_tokens INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to initialize SQLite LLM cache: {e}")

    def get(self, cache_key: str) -> Optional[str]:
        with self._lock:
            if cache_key in self._memory_cache:
                return self._memory_cache[cache_key]

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT response_json FROM prompt_cache WHERE cache_key = ?", (cache_key,))
                row = cursor.fetchone()
                if row:
                    val = row[0]
                    with self._lock:
                        self._memory_cache[cache_key] = val
                    return val
        except Exception as e:
            logger.warning(f"Error reading LLM cache: {e}")
        return None

    def set(self, cache_key: str, response_json: str, model: str, prompt_tokens: int, completion_tokens: int):
        with self._lock:
            self._memory_cache[cache_key] = response_json

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO prompt_cache 
                    (cache_key, response_json, model, prompt_tokens, completion_tokens)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cache_key, response_json, model, prompt_tokens, completion_tokens)
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Error writing to LLM cache: {e}")

    def clear(self):
        with self._lock:
            self._memory_cache.clear()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM prompt_cache")
                conn.commit()
        except Exception as e:
            logger.warning(f"Error clearing LLM cache: {e}")


_llm_cache = LLMCache()


def get_llm_cache() -> LLMCache:
    return _llm_cache


def clear_llm_cache():
    _llm_cache.clear()


def get_device() -> str:
    """Detect available accelerator: CUDA -> CPU."""
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def get_embedding_model():
    """Lazy load SentenceTransformer embedding model."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        device = get_device()
        _embedding_model = SentenceTransformer(settings.EMBED_MODEL, device=device)
    return _embedding_model


def get_tokenizer():
    """Lazy load tokenizer for exact token counting."""
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer, logging as tf_logging
        tf_logging.set_verbosity_error()
        _tokenizer = AutoTokenizer.from_pretrained(settings.EMBED_MODEL)
    return _tokenizer


def count_tokens(text: str) -> int:
    """Count tokens using the embedding model's tokenizer."""
    if not text:
        return 0
    tokenizer = get_tokenizer()
    return len(tokenizer.encode(text, add_special_tokens=False, truncation=False))


def get_genai_client():
    """Lazy load Google GenAI client."""
    global _genai_client
    if _genai_client is None:
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set GEMINI_API_KEY in .env"
            )
        from google import genai
        _genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _genai_client


def embed_local(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Generate normalized embeddings using local SentenceTransformer."""
    if not texts:
        return []

    model = get_embedding_model()

    # Prepend query instruction for BGE search queries only
    if is_query and "bge" in settings.EMBED_MODEL.lower():
        input_texts = [f"{BGE_QUERY_PREFIX}{t}" for t in texts]
    else:
        input_texts = texts

    # Encode with normalized embeddings
    embeddings = model.encode(
        input_texts,
        batch_size=settings.EMBED_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()


def _retry_log(retry_state):
    attempt = retry_state.attempt_number
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    sleep_time = retry_state.next_action.sleep if retry_state.next_action else 0
    logger.warning(
        f"[LLM] Per-minute rate limit (429) or transient error on attempt {attempt}: {exc}. "
        f"Retrying with exponential backoff in {sleep_time:.1f}s..."
    )


@retry(
    stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception(is_retryable_llm_error),
    before_sleep=_retry_log,
    reraise=True,
)
def embed_gemini(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Generate embeddings using Gemini API with retry and backoff."""
    if not texts:
        return []
    client = get_genai_client()
    task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"

    embeddings: List[List[float]] = []
    # Gemini embed batch
    for i in range(0, len(texts), settings.EMBED_BATCH_SIZE):
        batch = texts[i:i + settings.EMBED_BATCH_SIZE]
        try:
            result = client.models.embed_content(
                model=settings.EMBED_MODEL,
                contents=batch,
                config={"task_type": task_type, "output_dimensionality": settings.EMBED_DIM}
            )
            for emb in result.embeddings:
                embeddings.append(emb.values)
            _usage_tracker.record_call(prompt_tokens=len(batch) * 30, completion_tokens=0)
        except Exception as e:
            if is_daily_quota_error(e):
                logger.error(DAILY_QUOTA_ERROR_MESSAGE)
                raise GeminiDailyQuotaError(DAILY_QUOTA_ERROR_MESSAGE) from e
            raise
    return embeddings


def embed(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Route embedding to configured provider (local or gemini)."""
    if settings.EMBED_PROVIDER.lower() == "gemini":
        return embed_gemini(texts, is_query=is_query)
    return embed_local(texts, is_query=is_query)


def embed_one(text: str, is_query: bool = False) -> List[float]:
    """Embed a single text string."""
    results = embed([text], is_query=is_query)
    return results[0] if results else []


@retry(
    stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception(is_retryable_llm_error),
    before_sleep=_retry_log,
    reraise=True,
)
def _call_gemini_generate_api(client, target_model: str, prompt: str, config: Any) -> Any:
    """Internal helper to call Gemini API with per-minute retry and daily-quota guard."""
    try:
        return client.models.generate_content(
            model=target_model,
            contents=prompt,
            config=config,
        )
    except Exception as e:
        if is_daily_quota_error(e):
            logger.error(DAILY_QUOTA_ERROR_MESSAGE)
            raise GeminiDailyQuotaError(DAILY_QUOTA_ERROR_MESSAGE) from e
        raise


def _clean_json_text(raw_text: str) -> str:
    """Clean markdown code block wrappers from JSON string."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def generate_json(
    prompt: str,
    schema: Optional[Any] = None,
    system_instruction: Optional[str] = None,
    model: Optional[str] = None,
    use_cache: bool = True,
) -> Any:
    """
    Generate structured JSON response using Gemini with retries, exponential backoff,
    caching for identical prompts, token counting, and daily quota guards.
    """
    target_model = model or settings.GEN_MODEL

    # Compute deterministic cache key
    if schema is not None:
        if hasattr(schema, "model_json_schema"):
            schema_key = json.dumps(schema.model_json_schema(), sort_keys=True)
        elif hasattr(schema, "__name__"):
            schema_key = schema.__name__
        else:
            schema_key = str(schema)
    else:
        schema_key = ""

    key_raw = f"{target_model}\n{system_instruction or ''}\n{schema_key}\n{prompt}"
    cache_key = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

    # Check cache first
    if use_cache:
        cached_val = _llm_cache.get(cache_key)
        if cached_val is not None:
            _usage_tracker.record_cache_hit()
            try:
                return json.loads(cached_val)
            except Exception:
                pass

    client = get_genai_client()

    from google.genai import types
    config_args: Dict[str, Any] = {
        "response_mime_type": "application/json",
        "temperature": 0.2,
    }
    if system_instruction:
        config_args["system_instruction"] = system_instruction
    if schema is not None:
        config_args["response_schema"] = schema

    config = types.GenerateContentConfig(**config_args)

    try:
        response = _call_gemini_generate_api(client, target_model, prompt, config)
    except (GeminiDailyQuotaError, Exception) as e:
        if is_daily_quota_error(e):
            raise GeminiDailyQuotaError(DAILY_QUOTA_ERROR_MESSAGE) from e
        raise

    # Extract token usage metadata
    usage = getattr(response, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
    total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + completion_tokens)

    # Record API call and tokens
    _usage_tracker.record_call(prompt_tokens, completion_tokens, total_tokens)

    raw_text = response.text or "{}"
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        cleaned = _clean_json_text(raw_text)
        parsed = json.loads(cleaned)

    # Cache response
    if use_cache:
        _llm_cache.set(
            cache_key=cache_key,
            response_json=json.dumps(parsed),
            model=target_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    return parsed
