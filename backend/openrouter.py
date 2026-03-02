"""LLM API client — routes model requests through the multi-provider layer.

This module maintains the same public API as before but now delegates to
the appropriate provider (OpenRouter, Ollama, Groq, etc.) based on model ID prefix.
"""

import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from dotenv import load_dotenv

load_dotenv()

from .providers import resolve_provider


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    connection_timeout: Optional[float] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Query a single model. Routes to appropriate provider based on model ID prefix."""
    provider, actual_model = resolve_provider(model)
    return await provider.query(
        actual_model, messages,
        timeout=timeout, max_tokens=max_tokens, temperature=temperature,
    )


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

    for attempt in range(max_retries + 1):
        try:
            result = await query_model(model, messages, timeout=timeout, temperature=temperature)
            if result:
                return result
        except Exception as e:
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
    """Query a model with streaming. Routes to appropriate provider."""
    provider, actual_model = resolve_provider(model)
    async for chunk in provider.query_streaming(
        actual_model, messages,
        timeout=timeout, on_token=on_token, max_tokens=max_tokens, temperature=temperature,
    ):
        yield chunk


async def validate_openrouter_models(model_ids: List[str]) -> Dict[str, bool]:
    """Check which models are available. Groups by provider for validation."""
    from .providers import resolve_provider as _resolve
    # Group models by provider
    by_provider = {}
    for mid in model_ids:
        provider, actual = _resolve(mid)
        key = id(provider)
        if key not in by_provider:
            by_provider[key] = (provider, [])
        by_provider[key][1].append((mid, actual))

    results = {}
    for _, (provider, models) in by_provider.items():
        actual_ids = [actual for _, actual in models]
        validation = await provider.validate_models(actual_ids)
        for (original_id, actual_id) in models:
            results[original_id] = validation.get(actual_id, False)

    return results
