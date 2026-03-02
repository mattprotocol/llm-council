"""OpenRouter provider — routes all standard model IDs through OpenRouter API."""

import httpx
import json
import os
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from .base import LLMProvider

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


class OpenRouterProvider(LLMProvider):
    def __init__(self):
        self.base_url = OPENROUTER_BASE_URL
        self.api_key = OPENROUTER_API_KEY

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/mattprotocol/llm-council",
            "X-Title": "LLM Council",
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
            timeout = 120
        headers = self._headers()
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens or 4096}
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            timeout_config = httpx.Timeout(connect=30, read=timeout, write=timeout, pool=timeout)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]["message"]
                content = choice.get("content", "")
                reasoning_content = choice.get("reasoning_content", "")
                if not content and reasoning_content:
                    content = reasoning_content
                return {
                    "content": content,
                    "reasoning_content": reasoning_content,
                    "reasoning_details": choice.get("reasoning_details"),
                    "usage": data.get("usage", {}),
                }
        except Exception as e:
            print(f"OpenRouter error querying {model}: {e}")
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
            timeout = 120
        headers = self._headers()
        payload = {"model": model, "messages": messages, "stream": True, "max_tokens": max_tokens or 4096}
        if temperature is not None:
            payload["temperature"] = temperature

        content_buffer = ""
        reasoning_buffer = ""
        captured_usage = {}

        try:
            timeout_config = httpx.Timeout(connect=30, read=None, write=60.0, pool=60.0)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions",
                    headers=headers, json=payload,
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
                            chunk_usage = data.get("usage")
                            if chunk_usage:
                                captured_usage = chunk_usage
                            delta = data.get("choices", [{}])[0].get("delta", {})

                            reasoning_delta = delta.get("reasoning_content", "")
                            if reasoning_delta:
                                reasoning_buffer += reasoning_delta
                                if on_token:
                                    on_token(reasoning_delta, "thinking", reasoning_buffer)
                                yield {"type": "thinking", "delta": reasoning_delta, "content": reasoning_buffer}

                            content_delta = delta.get("content", "")
                            if content_delta:
                                content_buffer += content_delta
                                if on_token:
                                    on_token(content_delta, "token", content_buffer)
                                yield {"type": "token", "delta": content_delta, "content": content_buffer}
                        except json.JSONDecodeError:
                            continue

            yield {"type": "complete", "content": content_buffer, "reasoning_content": reasoning_buffer, "usage": captured_usage}
        except Exception as e:
            print(f"OpenRouter streaming error for {model}: {e}")
            yield {"type": "error", "error": str(e), "content": content_buffer, "reasoning_content": reasoning_buffer, "usage": captured_usage}

    async def validate_models(self, model_ids: List[str]) -> Dict[str, bool]:
        headers = self._headers()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.get(f"{self.base_url}/models", headers=headers)
                response.raise_for_status()
                data = response.json()
                available = {m["id"] for m in data.get("data", [])}
                return {mid: mid in available for mid in model_ids}
        except Exception as e:
            print(f"Error validating models: {e}")
            return {mid: False for mid in model_ids}
