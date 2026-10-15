import asyncio
from google import genai
from google.genai import types
from .config import get_settings

_settings = get_settings()
_client = genai.Client(api_key=_settings.google_api_key) if _settings.google_api_key else None


async def embed_text(text: str) -> list[float] | None:
    if not _client:
        return None
    def _call():
        response = _client.models.embed_content(
            model=_settings.embedding_model,
            contents=text[:6000],
            config=types.EmbedContentConfig(output_dimensionality=_settings.embedding_dimensions),
        )
        if not response.embeddings:
            return None
        return list(response.embeddings[0].values)
    return await asyncio.to_thread(_call)
