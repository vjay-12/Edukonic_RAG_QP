import json
from typing import List, Dict, Any, Optional
import torch
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.config import settings

# Global singletons
_embedding_model = None
_tokenizer = None
_genai_client = None

# BGE retrieval query instruction
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

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
        from transformers import AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(settings.EMBED_MODEL)
    return _tokenizer

def count_tokens(text: str) -> int:
    """Count tokens using the embedding model's tokenizer."""
    if not text:
        return 0
    tokenizer = get_tokenizer()
    return len(tokenizer.encode(text, add_special_tokens=False))

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

def _is_retryable_error(exc: BaseException) -> bool:
    """Check if exception is a rate limit or transient server error."""
    msg = str(exc).lower()
    return any(err in msg for err in ["429", "resource_exhausted", "503", "unavailable", "500", "internal"])

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

@retry(
    stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(_is_retryable_error),
    reraise=True,
)
def embed_gemini(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Generate embeddings using Gemini API."""
    if not texts:
        return []
    client = get_genai_client()
    task_type = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"

    embeddings: List[List[float]] = []
    # Gemini embed batch
    for i in range(0, len(texts), settings.EMBED_BATCH_SIZE):
        batch = texts[i:i + settings.EMBED_BATCH_SIZE]
        result = client.models.embed_content(
            model=settings.EMBED_MODEL,
            contents=batch,
            config={"task_type": task_type, "output_dimensionality": settings.EMBED_DIM}
        )
        for emb in result.embeddings:
            embeddings.append(emb.values)
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
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(_is_retryable_error),
    reraise=True,
)
def generate_json(
    prompt: str,
    schema: Optional[Any] = None,
    system_instruction: Optional[str] = None,
    model: Optional[str] = None,
) -> Any:
    """Generate structured JSON response using Gemini with retries."""
    client = get_genai_client()
    target_model = model or settings.GEN_MODEL

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

    response = client.models.generate_content(
        model=target_model,
        contents=prompt,
        config=config,
    )

    raw_text = response.text or "{}"
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Fallback strip code blocks if present
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())
