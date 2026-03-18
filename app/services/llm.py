import logging

from groq import Groq

from app.config import settings

logger = logging.getLogger(__name__)

groq_client = Groq(api_key=settings.groq_api_key)

SYSTEM_PROMPT = """You are a helpful assistant that answers questions based ONLY on the provided context.

Rules:
- Answer ONLY using information from the provided context chunks.
- If the context doesn't contain enough information, say so clearly.
- Cite the source document and page number for each piece of information you use.
- Keep answers concise and well-structured.
- Never make up information that isn't in the context."""


def build_prompt(query: str, chunks: list[dict]) -> str:
    """Build the user prompt with context chunks and source citations."""
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk['filename']}, Page {chunk['page']}]\n{chunk['chunk_text']}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    return f"""Context:
{context_block}

Question: {query}

Provide a clear, well-cited answer based on the context above."""


def call_groq(query: str, chunks: list[dict]) -> str:
    """Send the prompt to Groq and return the generated answer."""
    user_prompt = build_prompt(query, chunks)

    try:
        response = groq_client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.exception("Groq API call failed: %s", e)
        raise
