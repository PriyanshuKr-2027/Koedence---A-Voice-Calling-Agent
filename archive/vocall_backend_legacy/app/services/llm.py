import logging
from typing import Any, Dict, List, Optional, Union
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
MODEL_NAME = "llama-3.3-70b-versatile"


class LLMService:
    """
    Stateless LLM service that wraps Groq and Cerebras via their
    OpenAI-compatible chat completions endpoint.
    Supports tool / function calling and automatic fallback.
    """

    async def generate(
        self,
        prompt: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        api_keys: Optional[Dict[str, str]] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Generates a completion from the LLM for the given prompt + message history.
        If tools parameter is supplied, returns a dict with content and optional tool_calls.
        """
        api_keys = api_keys or {}

        groq_key = (
            api_keys.get("groq_api_key")
            or api_keys.get("groq")
            or settings.GROQ_API_KEY
        )
        cerebras_key = (
            api_keys.get("cerebras_api_key")
            or api_keys.get("cerebras")
            or settings.CEREBRAS_API_KEY
        )

        payload = self._build_payload(prompt, messages or [], temperature, max_tokens, tools)

        # ---- 1. Try Groq ----
        if groq_key:
            try:
                logger.debug("LLM: calling Groq %s", MODEL_NAME)
                return await self._call_provider(
                    base_url=GROQ_BASE_URL,
                    api_key=groq_key,
                    payload=payload,
                    has_tools=bool(tools),
                )
            except RateLimitError:
                logger.warning("Groq rate-limited (429) — falling back to Cerebras")
            except Exception as exc:
                logger.error("Groq request failed: %s — trying Cerebras", exc)
        else:
            logger.debug("Groq API key not set, trying Cerebras directly")

        # ---- 2. Fallback: Cerebras ----
        if cerebras_key:
            try:
                logger.debug("LLM: calling Cerebras %s", MODEL_NAME)
                return await self._call_provider(
                    base_url=CEREBRAS_BASE_URL,
                    api_key=cerebras_key,
                    payload=payload,
                    has_tools=bool(tools),
                )
            except RateLimitError:
                raise RuntimeError("Both Groq and Cerebras are rate-limited. Retry later.")
            except Exception as exc:
                raise RuntimeError(f"Cerebras request also failed: {exc}") from exc

        raise RuntimeError(
            "No LLM API key available. Configure GROQ_API_KEY or CEREBRAS_API_KEY."
        )

    @staticmethod
    def _build_payload(
        prompt: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        """Assembles the OpenAI-format request body."""
        chat_messages = [{"role": "system", "content": prompt}] + messages
        payload = {
            "model": MODEL_NAME,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    @staticmethod
    async def _call_provider(
        base_url: str, api_key: str, payload: dict, has_tools: bool = False
    ) -> Union[str, Dict[str, Any]]:
        """
        Makes a single HTTP POST to the provider's /chat/completions endpoint.
        Raises RateLimitError on HTTP 429, HTTPStatusError on other 4xx/5xx.
        """
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 429:
            raise RateLimitError(f"Rate limit hit at {base_url}")

        response.raise_for_status()

        data = response.json()
        try:
            msg = data["choices"][0]["message"]
            if has_tools or msg.get("tool_calls"):
                return {
                    "content": msg.get("content") or "",
                    "tool_calls": msg.get("tool_calls"),
                }
            return msg.get("content") or ""
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Unexpected LLM response shape: {data}") from exc


class RateLimitError(Exception):
    """Raised when a provider returns HTTP 429."""


# Module-level singleton
llm_service = LLMService()
