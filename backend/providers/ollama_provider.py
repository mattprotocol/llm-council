"""Ollama provider — routes to local Ollama server for on-device models."""

import httpx
import json
import os
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from .base import LLMProvider

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaProvider(LLMProvider):
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL

    async def query(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        if timeout is None:
            timeout = 300  # Ollama can be slow for large models
        payload = {"model": model, "messages": messages, "stream": False}
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options

        try:
            timeout_config = httpx.Timeout(connect=10, read=timeout, write=60, pool=timeout)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content", "")
                # Ollama provides eval_count and prompt_eval_count
                usage = {}
                if "eval_count" in data:
                    usage["completion_tokens"] = data["eval_count"]
                if "prompt_eval_count" in data:
                    usage["prompt_tokens"] = data["prompt_eval_count"]
                if usage:
                    usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                return {"content": content, "reasoning_content": "", "usage": usage}
        except Exception as e:
            print(f"Ollama error querying {model}: {e}")
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
            timeout = 300
        payload = {"model": model, "messages": messages, "stream": True}
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options

        content_buffer = ""

        try:
            timeout_config = httpx.Timeout(connect=10, read=None, write=60.0, pool=60.0)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("done"):
                                usage = {}
                                if "eval_count" in data:
                                    usage["completion_tokens"] = data["eval_count"]
                                if "prompt_eval_count" in data:
                                    usage["prompt_tokens"] = data["prompt_eval_count"]
                                if usage:
                                    usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                                yield {"type": "complete", "content": content_buffer, "reasoning_content": "", "usage": usage}
                                return

                            content_delta = data.get("message", {}).get("content", "")
                            if content_delta:
                                content_buffer += content_delta
                                if on_token:
                                    on_token(content_delta, "token", content_buffer)
                                yield {"type": "token", "delta": content_delta, "content": content_buffer}
                        except json.JSONDecodeError:
                            continue

            yield {"type": "complete", "content": content_buffer, "reasoning_content": "", "usage": {}}
        except Exception as e:
            print(f"Ollama streaming error for {model}: {e}")
            yield {"type": "error", "error": str(e), "content": content_buffer, "reasoning_content": "", "usage": {}}

    async def validate_models(self, model_ids: List[str]) -> Dict[str, bool]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                available = {m["name"] for m in data.get("models", [])}
                # Also match without tag suffix (e.g., "llama3.2" matches "llama3.2:latest")
                return {mid: mid in available or f"{mid}:latest" in available for mid in model_ids}
        except Exception as e:
            print(f"Ollama validation error: {e}")
            return {mid: False for mid in model_ids}
