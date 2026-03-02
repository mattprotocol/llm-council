"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable


class LLMProvider(ABC):
    """Base class for all LLM provider implementations.

    Each provider handles a specific API backend (OpenRouter, Ollama, Groq, etc.).
    Providers are selected based on model ID prefixes:
      - Default (no prefix): OpenRouter
      - ollama: → Ollama local server
      - groq: → Groq API
      - openai-direct: → OpenAI API directly
      - anthropic-direct: → Anthropic API directly
      - custom:<base_url>: → Any OpenAI-compatible endpoint
    """

    @abstractmethod
    async def query(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Query a model and return the complete response.

        Returns dict with: content, reasoning_content, usage
        """
        ...

    @abstractmethod
    async def query_streaming(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: Optional[float] = None,
        on_token: Optional[Callable] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Query a model with streaming, yielding token chunks.

        Yields dicts with type: "thinking" | "token" | "complete" | "error"
        """
        ...

    async def validate_models(self, model_ids: List[str]) -> Dict[str, bool]:
        """Check which models are available. Default returns True for all."""
        return {mid: True for mid in model_ids}
