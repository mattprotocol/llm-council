## Context
The LLM Council currently processes every query through either direct response or full council deliberation. By integrating with the Graphiti MCP server (already configured), we can:
1. Build a knowledge graph of all conversations
2. Check memory before invoking LLMs/tools for potential instant responses
3. Track relationships between facts and their recency

## Goals / Non-Goals
**Goals:**
- Record all messages (user, LLM responses) to Graphiti during normal workflow
- Implement confidence scoring for memory-based responses
- Add configurable confidence thresholds and model settings
- Provide fast-path responses when memory confidence is high

**Non-Goals:**
- Replace existing MCP tool functionality
- Modify Graphiti MCP server itself
- UI changes for memory visualization (future work)

## Decisions

### Memory Recording Strategy
- **Decision**: Record messages asynchronously after successful responses
- **Rationale**: Non-blocking, doesn't slow down response time
- **Alternative considered**: Synchronous recording - rejected due to latency impact

### Confidence Scoring Approach
- **Decision**: Use configurable LLM to evaluate memory relevance and freshness
- **Components**:
  1. Query Graphiti for related memories (search_nodes, search_facts)
  2. Pass memories + original query to confidence LLM
  3. Score based on: memory relevance, recency, relationship strength
- **Threshold**: Configurable, default 0.8 (80% confidence)
- **Alternative considered**: Pure heuristic scoring - rejected due to limited accuracy

### Memory Structure
Episodes will be recorded with:
- `name`: Conversation title or query summary
- `episode_body`: Full message content
- `source`: "llm_council" 
- `source_description`: Role (user/council_member/chairman) + model name
- `reference_time`: Timestamp of message

### Confidence Model Configuration
```json
{
  "models": {
    "confidence": {
      "id": "",
      "name": "Memory Confidence Scorer",
      "description": "Model for scoring memory relevance (empty = use chairman)",
      "threshold": 0.8,
      "max_memory_age_days": 30
    }
  }
}
```

## Risks / Trade-offs
- **Risk**: Graphiti server unavailability → **Mitigation**: Graceful fallback to normal flow
- **Risk**: Memory staleness → **Mitigation**: Recency weighting in confidence scoring
- **Trade-off**: Additional latency for memory check vs potential instant responses

## Migration Plan
1. Add memory service module (non-breaking)
2. Add config fields (backwards compatible with defaults)
3. Integrate memory recording (async, non-blocking)
4. Add memory check to routing (opt-in via config)

## Open Questions
- Should we expose memory status in API responses?
- Should there be a UI toggle to disable memory-based responses?
