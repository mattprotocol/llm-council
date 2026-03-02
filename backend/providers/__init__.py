"""Multi-provider routing layer.

Model IDs are routed to the appropriate provider based on prefix:
  - Default (no prefix, e.g. "anthropic/claude-opus-4"): OpenRouter
  - "ollama:" prefix (e.g. "ollama:llama3.2"): Local Ollama server
  - "groq:" prefix (e.g. "groq:llama-3.1-70b"): Groq API
  - "direct:openai:" prefix: OpenAI API directly
  - "direct:mistral:" prefix: Mistral API directly
  - "direct:deepseek:" prefix: DeepSeek API directly
  - "custom:<base_url>:" prefix: Any OpenAI-compatible endpoint

The routing is transparent — callers use the full model ID and this module
handles stripping the prefix and selecting the right provider.
"""

import os
from typing import Optional, Tuple
from .base import LLMProvider
from .openrouter_provider import OpenRouterProvider
from .ollama_provider import OllamaProvider
from .groq_provider import GroqProvider
from .openai_compat_provider import OpenAICompatProvider, get_direct_provider

# Singleton instances (created on first use)
_provider_cache = {}


def _get_or_create(key: str, factory) -> LLMProvider:
    """Get a cached provider or create one."""
    if key not in _provider_cache:
        _provider_cache[key] = factory()
    return _provider_cache[key]


def resolve_provider(model_id: str) -> Tuple[LLMProvider, str]:
    """Resolve a model ID to (provider, actual_model_name).

    The actual_model_name is the model ID with the provider prefix stripped,
    which is what gets sent to the provider's API.

    Examples:
      "anthropic/claude-opus-4" → (OpenRouterProvider, "anthropic/claude-opus-4")
      "ollama:llama3.2"        → (OllamaProvider, "llama3.2")
      "groq:llama-3.1-70b"    → (GroqProvider, "llama-3.1-70b")
      "direct:openai:gpt-4o"  → (OpenAICompatProvider, "gpt-4o")
      "custom:http://localhost:8080:my-model" → (OpenAICompatProvider, "my-model")
    """
    # Ollama prefix
    if model_id.startswith("ollama:"):
        provider = _get_or_create("ollama", OllamaProvider)
        return provider, model_id[7:]  # Strip "ollama:"

    # Groq prefix
    if model_id.startswith("groq:"):
        provider = _get_or_create("groq", GroqProvider)
        return provider, model_id[5:]  # Strip "groq:"

    # Direct provider prefix (e.g., "direct:openai:gpt-4o")
    if model_id.startswith("direct:"):
        rest = model_id[7:]  # Strip "direct:"
        parts = rest.split(":", 1)
        if len(parts) == 2:
            provider_name, actual_model = parts
            provider = get_direct_provider(provider_name)
            if provider:
                return provider, actual_model
            else:
                # Fall back to OpenRouter with the model mapped to provider/model format
                print(f"Warning: No API key for direct provider '{provider_name}', falling back to OpenRouter")
                fallback_model = f"{provider_name}/{actual_model}"
                provider = _get_or_create("openrouter", OpenRouterProvider)
                return provider, fallback_model

    # Custom endpoint prefix (e.g., "custom:http://localhost:8080:my-model")
    if model_id.startswith("custom:"):
        rest = model_id[7:]  # Strip "custom:"
        # Find the last colon that separates URL from model name
        # URL might contain colons (http://host:port), so find model name after last colon
        last_colon = rest.rfind(":")
        if last_colon > 0:
            base_url = rest[:last_colon]
            actual_model = rest[last_colon + 1:]
            api_key = os.getenv("CUSTOM_LLM_API_KEY", "")
            cache_key = f"custom:{base_url}"
            provider = _get_or_create(
                cache_key,
                lambda: OpenAICompatProvider(base_url=base_url, api_key=api_key, name="custom")
            )
            return provider, actual_model

    # Default: OpenRouter (handles standard model IDs like "anthropic/claude-opus-4")
    provider = _get_or_create("openrouter", OpenRouterProvider)
    return provider, model_id


def get_provider_name(model_id: str) -> str:
    """Get a human-readable provider name for a model ID."""
    if model_id.startswith("ollama:"):
        return "Ollama"
    if model_id.startswith("groq:"):
        return "Groq"
    if model_id.startswith("direct:"):
        parts = model_id[7:].split(":", 1)
        return parts[0].title() if parts else "Direct"
    if model_id.startswith("custom:"):
        return "Custom"
    return "OpenRouter"
