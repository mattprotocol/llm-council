# Change: Graphiti MCP Memory Integration

## Why
Enable persistent memory across conversations by integrating the Graphiti MCP server to:
1. Record all messages (user, council members, chairman) during both workflows
2. Use stored memories as a fast-path response option when confidence is high

## What Changes
- Add memory recording for all messages during council deliberation and direct answer workflows
- Add memory retrieval and confidence scoring before standard tool/LLM execution
- Add confidence model configuration in config.json (empty = use chairman as fallback)
- New memory service module for Graphiti interaction
- Memory-based response path when confidence exceeds threshold

## Impact
- Affected specs: new `memory-integration` capability
- Affected code: 
  - `backend/council.py` - Add memory recording hooks
  - `backend/memory_service.py` - New module for Graphiti interaction
  - `backend/main.py` - Add memory check before routing
  - `config.json` - Add confidence model configuration
