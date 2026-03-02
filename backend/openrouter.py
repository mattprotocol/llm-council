"""OpenRouter API client for making LLM requests via OpenRouter."""

import httpx
import asyncio
import os
import json
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


def _get_headers() -> Dict[str, str]:
    """Get headers for OpenRouter API requests."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/mattprotocol/llm-council",
        "X-Title": "LLM Council",
    }


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    connection_timeout: Optional[float] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Query a single model via OpenRouter API."""
    if timeout is None:
        timeout = 120
    if connection_timeout is None:
        connection_timeout = 30

    headers = _get_headers()
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens or 4096}
    if temperature is not None:
        payload["temperature"] = temperature

    try:
        timeout_config = httpx.Timeout(
            connect=connection_timeout, read=timeout, write=timeout, pool=timeout
        )
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]["message"]
            content = choice.get("content", "")
            reasoning_content = choice.get("reasoning_content", "")

            # If content is empty but reasoning exists (thinking models), use reasoning
            if not content and reasoning_content:
                content = reasoning_content

            usage = data.get("usage", {})
            return {
                "content": content,
                "reasoning_content": reasoning_content,
                "reasoning_details": choice.get("reasoning_details"),
                "usage": usage,
            }
    except httpx.HTTPStatusError as e:
        print(f"HTTP error querying {model}: {e}")
        print(f"Response: {e.response.text[:500]}")
        return None
    except Exception as e:
        print(f"Error querying {model}: {e}")
        return None


async def query_model_with_retry(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
    for_title: bool = False,
    for_evaluation: bool = False,
    temperature: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Query a model with retry logic."""
    if timeout is None:
        timeout = 30 if for_evaluation else (60 if for_title else 120)
    if max_retries is None:
        max_retries = 1

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = await query_model(model, messages, timeout=timeout, temperature=temperature)
            if result:
                return result
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"Retry {attempt+1} for {model} in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                print(f"Model {model} failed after {max_retries+1} attempts: {e}")

    return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query multiple models in parallel."""
    tasks = [query_model_with_retry(model, messages, timeout=timeout) for model in models]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    result = {}
    for model, response in zip(models, responses):
        if isinstance(response, Exception):
            print(f"Exception for {model}: {response}")
            result[model] = None
        else:
            result[model] = response
    return result


async def query_model_streaming(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    connection_timeout: Optional[float] = None,
    on_token: Optional[Callable[[str, str, Optional[str]], None]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Query a model with streaming enabled, yielding tokens as they arrive."""
    if timeout is None:
        timeout = 120
    if connection_timeout is None:
        connection_timeout = 30

    headers = _get_headers()
    payload = {"model": model, "messages": messages, "stream": True, "max_tokens": max_tokens or 4096}
    if temperature is not None:
        payload["temperature"] = temperature

    content_buffer = ""
    reasoning_buffer = ""
    captured_usage = {}

    try:
        timeout_config = httpx.Timeout(
            connect=connection_timeout, read=None, write=60.0, pool=60.0
        )
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            async with client.stream(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
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
        print(f"Streaming error for {model}: {e}")
        yield {"type": "error", "error": str(e), "content": content_buffer, "reasoning_content": reasoning_buffer, "usage": captured_usage}


async def validate_openrouter_models(model_ids: List[str]) -> Dict[str, bool]:
    """Check which models are available on OpenRouter."""
    headers = _get_headers()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.get(f"{OPENROUTER_BASE_URL}/models", headers=headers)
            response.raise_for_status()
            data = response.json()
            available = {m["id"] for m in data.get("data", [])}
            return {mid: mid in available for mid in model_ids}
    except Exception as e:
        print(f"Error validating models: {e}")
        return {mid: False for mid in model_ids}
