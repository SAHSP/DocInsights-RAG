"""
LLM Service
Default provider: OpenRouter (OpenAI-compatible API)
Pluggable: switch to OpenAI, Anthropic direct, or Ollama via settings.
"""
import logging
from typing import Optional

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Prompt Template ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a precise document assistant. Your job is to answer the user's question \
using ONLY the context provided below. 

Rules:
1. Base your answer strictly on the provided context. Do not use outside knowledge.
2. If the answer is not found in the context, say: "I could not find an answer to this question in the provided documents."
3. Be concise and factual. Cite the source (filename and page number) when possible.
4. If multiple sources contain relevant information, synthesize them clearly."""


def _build_user_prompt(query: str, parent_chunks: list[dict]) -> str:
    """Assemble the user-facing prompt with context blocks."""
    context_blocks = []
    for i, chunk in enumerate(parent_chunks, start=1):
        header = f"[Source {i}: {chunk.get('filename', 'Unknown')}, Page {chunk.get('page_number', '?')}]"
        context_blocks.append(f"{header}\n{chunk['chunk_text']}")

    context = "\n\n---\n\n".join(context_blocks)

    return f"""CONTEXT:
{context}

---

QUESTION:
{query}"""


# ── Client Factory ────────────────────────────────────────────────────────────

def _get_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> OpenAI:
    """Build an OpenAI-compatible client for any provider."""
    return OpenAI(
        api_key=api_key or settings.openrouter_api_key,
        base_url=base_url or settings.openrouter_base_url,
    )


# ── LLM Call ─────────────────────────────────────────────────────────────────

def generate_answer(
    query: str,
    parent_chunks: list[dict],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
) -> str:
    """
    Generate a grounded answer from the LLM.

    parent_chunks: list of dicts with keys: chunk_text, filename, page_number
    model:    override the default model from settings
    api_key:  override the default API key
    base_url: override the default base URL (for Ollama: http://localhost:11434/v1)

    Returns the answer string.
    """
    if not parent_chunks:
        return "No relevant context was found in the documents to answer this question."

    client    = _get_client(api_key=api_key, base_url=base_url)
    llm_model = model or settings.openrouter_model
    user_msg  = _build_user_prompt(query, parent_chunks)

    try:
        response = client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.1,    # low temp for factual retrieval tasks
            max_tokens=1024,
        )
        answer = response.choices[0].message.content or ""
        logger.info(f"LLM response received. Tokens used: {response.usage.total_tokens if response.usage else 'N/A'}")
        return answer.strip()

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise
