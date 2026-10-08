import json
import logging
import inspect
from typing import Optional, Dict, Any
import httpx

from app.core.config import settings
from app.services.emotion.mapping import CANONICAL_EMOTIONS, map_to_canonical_emotion

logger = logging.getLogger(__name__)

CANONICAL_LABELS_STR = ", ".join(CANONICAL_EMOTIONS)


async def analyze_text_emotion(
    transcript_chunk: str,
    groq_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Extracts emotion from text transcript using Groq in JSON mode.

    Supports English, Hindi, and Hinglish. Constrains dominant emotion to:
    angry, frustrated, sad, anxious, confused, neutral, calm, happy, other.

    Args:
        transcript_chunk: The text transcript of a single dialogue turn.
        groq_client: Groq client instance, API key string, or None (uses settings).

    Returns:
        dict: {"valence": float, "arousal": float, "dominant": str, "confidence": float}
        None: On any error or invalid input.
    """
    if not transcript_chunk or not isinstance(transcript_chunk, str) or not transcript_chunk.strip():
        return None

    system_prompt = (
        "Extract emotion from text. Return ONLY valid JSON.\n"
        f"Allowed dominant labels: {CANONICAL_LABELS_STR}.\n"
        "Note: transcript may be in English, Hindi, or Hinglish — analyze regardless of language."
    )
    user_prompt = (
        f"Analyze: '{transcript_chunk.strip()}'\n"
        f"Return: {{valence: float -1 to 1, arousal: float 0 to 1, dominant: string (must be one of: {CANONICAL_LABELS_STR}), confidence: float 0 to 1}}"
    )

    llm_model = settings.LLM_MODEL or "llama-3.3-70b-versatile"

    try:
        response_content: Optional[str] = None

        # 1. If groq_client has chat.completions.create signature (Groq SDK client)
        if groq_client and hasattr(groq_client, "chat") and hasattr(groq_client.chat, "completions"):
            create_fn = groq_client.chat.completions.create
            if inspect.iscoroutinefunction(create_fn):
                res = await create_fn(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
            else:
                res = create_fn(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
            response_content = res.choices[0].message.content

        # 2. If groq_client is an API key string or settings.GROQ_API_KEY is available
        else:
            api_key = groq_client if isinstance(groq_client, str) and groq_client.strip() else settings.GROQ_API_KEY
            if not api_key:
                logger.warning("Groq API key not provided for text emotion analysis")
                return None

            try:
                from groq import AsyncGroq
                client = AsyncGroq(api_key=api_key)
                res = await client.chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                response_content = res.choices[0].message.content
            except Exception as sdk_exc:
                logger.debug("Groq SDK call failed (%s), falling back to direct HTTP request", sdk_exc)
                # HTTP fallback via httpx
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                }
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    resp = await http_client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    response_content = data["choices"][0]["message"]["content"]

        if not response_content:
            return None

        # Parse JSON
        parsed = json.loads(response_content)
        if not isinstance(parsed, dict):
            return None

        valence = float(parsed.get("valence", 0.0))
        arousal = float(parsed.get("arousal", 0.5))
        raw_dominant = str(parsed.get("dominant", "neutral"))
        dominant = map_to_canonical_emotion(raw_dominant)
        confidence = float(parsed.get("confidence", 0.8))

        # Clamp range bounds
        valence = max(-1.0, min(1.0, valence))
        arousal = max(0.0, min(1.0, arousal))
        confidence = max(0.0, min(1.0, confidence))

        return {
            "valence": valence,
            "arousal": arousal,
            "dominant": dominant,
            "confidence": confidence,
        }

    except Exception as exc:
        logger.warning("analyze_text_emotion failed: %s", exc)
        return None
