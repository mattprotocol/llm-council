"""Groq provider — routes to Groq API for fast inference."""

import httpx
import json
import os
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from .base import LLMProvider

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(LLMProvider):
    """Groq uses an OpenAI-compatible API but with its own endpoint and key."""

    def __init__(self):
        self.base_url = GROQ_BASE_URL
        self.api_key = GROQ_API_KEY

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def query(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if timeout is None:
            timeout = 60
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens or 4096}
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            timeout_config = httpx.Timeout(connect=15, read=timeout, write=timeout, pool=timeout)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]["message"]
                return {
                    "content": choice.get("content", ""),
                    "reasoning_content": "",
                    "usage": data.get("usage", {}),
                }
        except Exception as e:
            print(f"Groq error querying {model}: {e}")
            return None

    async def query_streaming(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: Optional[float] = None,
        on_token: Optional[Callable] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if timeout is None:
            timeout = 60
        payload = {"model": model, "messages": messages, "stream": True, "max_tokens": max_tokens or 4096}
        if temperature is not None:
            payload["temperature"] = temperature

        content_buffer = ""
        captured_usage = {}

        try:
            timeout_config = httpx.Timeout(connect=15, read=None, write=60.0, pool=60.0)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions",
                    headers=self._headers(), json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if data.get("usage"):
                                captured_usage = data["usage"]
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content_delta = delta.get("content", "")
                            if content_delta:
                                content_buffer += content_delta
                                if on_token:
                                    on_token(content_delta, "token", content_buffer)
                                yield {"type": "token", "delta": content_delta, "content": content_buffer}
                        except json.JSONDecodeError:
                            continue

            yield {"type": "complete", "content": content_buffer, "reasoning_content": "", "usage": captured_usage}
        except Exception as e:
            print(f"Groq streaming error for {model}: {e}")
            yield {"type": "error", "error": str(e), "content": content_buffer, "reasoning_content": "", "usage": captured_usage}
