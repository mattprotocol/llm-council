"""LiteLLM multi-provider abstraction for LLM Council.

Routes models to their native APIs when direct API keys are available,
falls back to OpenRouter when they're not.
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from dotenv import load_dotenv

load_dotenv()

# Check which direct API keys are available
DIRECT_PROVIDERS = {}
if os.getenv("ANTHROPIC_API_KEY"):
    DIRECT_PROVIDERS["anthropic"] = True
if os.getenv("OPENAI_API_KEY"):
    DIRECT_PROVIDERS["openai"] = True
if os.getenv("GOOGLE_API_KEY"):
    DIRECT_PROVIDERS["google"] = True

# Try to import litellm if available
_litellm_available = False
try:
    import litellm
    litellm.drop_params = True
    _litellm_available = True
except ImportError:
    pass

# Import OpenRouter as fallback
from . import openrouter


def _should_use_direct(model: str) -> bool:
    """Check if we should use direct API for this model."""
    if not _litellm_available:
        return False
    provider = model.split("/")[0] if "/" in model else ""
    return provider in DIRECT_PROVIDERS


def _litellm_model_id(model: str) -> str:
    """Convert OpenRouter model ID to LiteLLM format if needed."""
    # Most OpenRouter IDs work directly with LiteLLM
    # But some need adjustment
    mapping = {
        "x-ai/grok-4": "xai/grok-4",
        "deepseek/deepseek-r1": "deepseek/deepseek-reasoner",
    }
    return mapping.get(model, model)


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    connection_timeout: Optional[float] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Query a model, routing to direct API or OpenRouter."""
    if _should_use_direct(model):
        try:
            litellm_id = _litellm_model_id(model)
            kwargs = {"model": litellm_id, "messages": messages}
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                kwargs["temperature"] = temperature
            if timeout:
                kwargs["timeout"] = timeout

            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content or ""
            reasoning = getattr(response.choices[0].message, "reasoning_content", "") or ""
            if not content and reasoning:
                content = reasoning
            return {"content": content, "reasoning_content": reasoning, "reasoning_details": None}
        except Exception as e:
            print(f"[LiteLLM] Direct API failed for {model}: {e}, falling back to OpenRouter")

    return await openrouter.query_model(
        model, messages, timeout=timeout, connection_timeout=connection_timeout,
        max_tokens=max_tokens, temperature=temperature
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
    """Query with retry, routing to direct API or OpenRouter."""
    if _should_use_direct(model):
        if max_retries is None:
            max_retries = 1
        for attempt in range(max_retries + 1):
            result = await query_model(model, messages, timeout=timeout, temperature=temperature)
            if result:
                return result
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
        # Fall through to OpenRouter on failure

    return await openrouter.query_model_with_retry(
        model, messages, timeout=timeout, max_retries=max_retries,
        for_title=for_title, for_evaluation=for_evaluation, temperature=temperature
    )


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query multiple models in parallel, routing each optimally."""
    tasks = [query_model_with_retry(model, messages, timeout=timeout) for model in models]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        model: (None if isinstance(resp, Exception) else resp)
        for model, resp in zip(models, responses)
    }


async def query_model_streaming(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    connection_timeout: Optional[float] = None,
    on_token: Optional[Callable] = None,
    max_tokens: Optional[int] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream from a model. Currently only OpenRouter streaming is supported."""
    # LiteLLM streaming is more complex; use OpenRouter for streaming
    async for chunk in openrouter.query_model_streaming(
        model, messages, timeout=timeout, connection_timeout=connection_timeout,
        on_token=on_token, max_tokens=max_tokens
    ):
        yield chunk
