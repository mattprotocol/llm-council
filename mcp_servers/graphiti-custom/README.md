# Graphiti Custom MCP Server

Custom fork of Graphiti MCP server with LM Studio support via custom `LMStudioClient`.

## Key Features

- **Strict JSON Schema** - Uses `additionalProperties: false` for LM Studio compatibility
- **Automatic retry** - Retries failed JSON parsing with error context
- **FalkorDB support** - Configured for FalkorDB at `redis://192.168.1.111:6379`

## Changes from upstream

1. Added `LMStudioClient` - Custom LLM client with strict JSON schema support
2. Added `lmstudio` provider option in `LLMClientFactory`
3. Added `openai_generic` provider for standard OpenAI-compatible servers

## Files

- `lmstudio_client.py` - Custom LLM client with strict JSON schema
- `factories.patch` - Patch to add lmstudio/openai_generic providers
- `schema.patch` - Patch to add OpenAIGenericProviderConfig
- `config.yaml` - Configuration for LM Studio + FalkorDB
- `Dockerfile` - Build container with patches applied

## Configuration

Edit `config.yaml`:

```yaml
llm:
  provider: lmstudio  # or openai_generic
  model: qwen2.5-14b-instruct
  temperature: 0.0
  max_tokens: 16384
  providers:
    openai_generic:
      api_key: "lms"
      api_url: "http://192.168.1.111:11434/v1"

database:
  provider: falkordb
  providers:
    falkordb:
      uri: "redis://192.168.1.111:6379"
```

## Build & Run

```bash
cd mcp_servers/graphiti-custom

# Build
docker build -t graphiti-custom .

# Run
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your-key \
  graphiti-custom
```

## JSON Schema Format

The `LMStudioClient` generates strict JSON schemas like:

```json
{
  "type": "json_schema",
  "json_schema": {
    "name": "ExtractedEntities",
    "strict": true,
    "schema": {
      "type": "object",
      "required": ["extracted_entities"],
      "additionalProperties": false,
      "properties": {
        "extracted_entities": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "entity_type_id"],
            "additionalProperties": false,
            "properties": {
              "name": {"type": "string"},
              "entity_type_id": {"type": "integer"}
            }
          }
        }
      }
    }
  }
}
```

## Testing

After running, test with:

```bash
cd /Users/max/llm-council
uv run python -m tests.test_graphiti
```
