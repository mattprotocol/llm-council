"""
Custom OpenAI Generic Client for LM Studio compatibility.

This client extends Graphiti's OpenAIGenericClient to ensure proper
JSON schema format that works with LM Studio's structured output.
"""

import json
import logging
import typing
from typing import Any, ClassVar

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from graphiti_core.prompts.models import Message
from graphiti_core.llm_client.client import LLMClient, get_extraction_language_instruction
from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from graphiti_core.llm_client.errors import RateLimitError, RefusalError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'qwen2.5-14b-instruct'


class LMStudioClient(LLMClient):
    """
    LLM Client optimized for LM Studio with proper JSON schema support.
    
    Key differences from OpenAIGenericClient:
    - Uses strict JSON schema format with additionalProperties: false
    - Handles LM Studio's response format requirements
    """

    MAX_RETRIES: ClassVar[int] = 3

    def __init__(
        self,
        config: LLMConfig | None = None,
        cache: bool = False,
        client: typing.Any = None,
        max_tokens: int = 16384,
    ):
        if cache:
            raise NotImplementedError('Caching is not implemented')

        if config is None:
            config = LLMConfig()

        super().__init__(config, cache)
        self.max_tokens = max_tokens

        if client is None:
            self.client = AsyncOpenAI(api_key=config.api_key or "not-needed", base_url=config.base_url)
        else:
            self.client = client

    def _pydantic_to_strict_schema(self, model: type[BaseModel]) -> dict[str, Any]:
        """Convert Pydantic model to strict JSON schema for LM Studio."""
        schema = model.model_json_schema()
        
        # Make schema strict - add additionalProperties: false to all objects
        def make_strict(obj: dict) -> dict:
            if obj.get('type') == 'object':
                obj['additionalProperties'] = False
            
            # Process nested properties
            if 'properties' in obj:
                for prop in obj['properties'].values():
                    if isinstance(prop, dict):
                        make_strict(prop)
            
            # Process array items
            if 'items' in obj and isinstance(obj['items'], dict):
                make_strict(obj['items'])
            
            # Process $defs
            if '$defs' in obj:
                for def_schema in obj['$defs'].values():
                    if isinstance(def_schema, dict):
                        make_strict(def_schema)
            
            return obj
        
        return make_strict(schema)

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        openai_messages: list[ChatCompletionMessageParam] = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == 'user':
                openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system':
                openai_messages.append({'role': 'system', 'content': m.content})
        
        try:
            # Prepare response format
            response_format: dict[str, Any] | None = None
            
            if response_model is not None:
                schema_name = getattr(response_model, '__name__', 'response')
                strict_schema = self._pydantic_to_strict_schema(response_model)
                
                # LM Studio format for structured output
                response_format = {
                    'type': 'json_schema',
                    'json_schema': {
                        'name': schema_name,
                        'strict': True,
                        'schema': strict_schema,
                    },
                }
                
                logger.debug(f"Using JSON schema for {schema_name}: {json.dumps(strict_schema, indent=2)}")
            else:
                # Fall back to basic JSON mode
                response_format = {'type': 'json_object'}

            response = await self.client.chat.completions.create(
                model=self.model or DEFAULT_MODEL,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format=response_format,
            )
            
            result = response.choices[0].message.content or '{}'
            logger.debug(f"Raw LLM response: {result[:500]}...")
            
            return json.loads(result)
            
        except openai.RateLimitError as e:
            raise RateLimitError from e
        except json.JSONDecodeError as e:
            logger.error(f'Invalid JSON in LLM response: {e}')
            raise
        except Exception as e:
            logger.error(f'Error in generating LLM response: {e}')
            raise

    async def generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        model_size: ModelSize = ModelSize.medium,
        group_id: str | None = None,
        prompt_name: str | None = None,
    ) -> dict[str, typing.Any]:
        if max_tokens is None:
            max_tokens = self.max_tokens

        # Add multilingual extraction instructions
        messages[0].content += get_extraction_language_instruction(group_id)

        with self.tracer.start_span('llm.generate') as span:
            attributes = {
                'llm.provider': 'lmstudio',
                'model.size': model_size.value,
                'max_tokens': max_tokens,
            }
            if prompt_name:
                attributes['prompt.name'] = prompt_name
            span.add_attributes(attributes)

            retry_count = 0
            last_error = None

            while retry_count <= self.MAX_RETRIES:
                try:
                    response = await self._generate_response(
                        messages, response_model, max_tokens=max_tokens, model_size=model_size
                    )
                    return response
                except (RateLimitError, RefusalError):
                    span.set_status('error', str(last_error))
                    raise
                except Exception as e:
                    last_error = e

                    if retry_count >= self.MAX_RETRIES:
                        logger.error(f'Max retries ({self.MAX_RETRIES}) exceeded. Last error: {e}')
                        span.set_status('error', str(e))
                        span.record_exception(e)
                        raise

                    retry_count += 1

                    # Add error context for retry
                    error_context = (
                        f'The previous response was invalid. '
                        f'Error: {e.__class__.__name__}: {str(e)}. '
                        f'Please respond with valid JSON matching the required schema.'
                    )

                    error_message = Message(role='user', content=error_context)
                    messages.append(error_message)
                    logger.warning(f'Retrying (attempt {retry_count}/{self.MAX_RETRIES}): {e}')

            span.set_status('error', str(last_error))
            raise last_error or Exception('Max retries exceeded')
