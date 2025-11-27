# Change 023: Intelligent Message Routing

## Summary

Before council members start deliberating, the chairman evaluates the message type to determine the appropriate response strategy. Simple factual questions or casual chat get direct answers from the chairman; complex questions requiring opinions, comparisons, or deliberation go through the full council process.

## Motivation

Not all user messages require the full 3-stage deliberation process:
- **Factual questions**: "What's 3 + 8?", "Who won the Nobel Prize in 2024?" - These have definitive answers
- **Casual chat**: "How are you?", "Hello" - Simple conversational responses
- **Tool-requiring queries**: "What's today's date?", "What's the weather?" - Need MCP tools first

These can be answered directly by the chairman, saving time and resources.

However, some messages benefit from deliberation:
- **Feedback requests**: "Review my code", "Is this argument sound?"
- **Opinion formation**: "Which framework is better for X?"
- **Comparisons**: "Compare Python vs JavaScript for backend"
- **Complex analysis**: Questions requiring multiple perspectives

## Proposed Changes

### 1. Message Classification Phase (New)

Add a pre-deliberation classification step where the chairman analyzes the message:

```python
async def classify_message(message: str, messages_history: list) -> dict:
    """
    Chairman classifies the message type.
    Returns: {
        "type": "factual" | "chat" | "deliberation",
        "requires_tools": bool,
        "reasoning": str
    }
    """
```

Classification prompt for chairman:
```
Analyze this user message and classify it:

Message: {message}

Respond with JSON:
{
  "type": "factual|chat|deliberation",
  "requires_tools": true/false,
  "reasoning": "brief explanation"
}

Classification guidelines:
- "factual": Questions with definitive answers (math, dates, facts, definitions)
- "chat": Casual conversation, greetings, simple acknowledgments
- "deliberation": Requests for opinions, comparisons, feedback, analysis, creative work
```

### 2. Routing Logic

```python
async def process_message(message: str, conversation_id: str) -> dict:
    # Phase 0: Classify message
    classification = await classify_message(message, history)
    
    # Phase 1: Tool evaluation (if needed)
    if classification["requires_tools"]:
        tool_result = await evaluate_and_execute_tools(message)
    
    # Phase 2: Route based on type
    if classification["type"] in ["factual", "chat"]:
        # Direct chairman response
        return await chairman_direct_response(message, tool_result)
    else:
        # Full deliberation process
        return await full_council_deliberation(message, tool_result)
```

### 3. Chairman Direct Response Mode

New function for direct responses (no council):
- Uses chairman model directly
- Includes tool results if applicable
- Returns simplified response structure (no stage1/stage2)

### 4. UI Updates

- Show classification result in response header
- Different visual treatment for direct vs deliberated responses
- Optional: Show "Deliberation skipped - simple query" message

## Implementation Details

### Files to Modify

1. **`backend/council.py`**
   - Add `classify_message()` function
   - Add `chairman_direct_response()` function
   - Modify `process_message()` to include routing

2. **`backend/main.py`**
   - Update message endpoint to use new routing
   - Return classification metadata in response

3. **`frontend/src/components/ChatInterface.jsx`**
   - Handle both response types (direct vs deliberated)
   - Show classification indicator

4. **`frontend/src/components/DirectResponse.jsx`** (new)
   - Component for displaying direct chairman responses

### Response Structure Changes

**Direct Response:**
```json
{
  "type": "direct",
  "classification": {
    "type": "factual",
    "requires_tools": false,
    "reasoning": "Simple math question"
  },
  "response": {
    "content": "3 + 8 = 11",
    "model": "chairman_model_name"
  },
  "tool_results": null
}
```

**Deliberated Response:**
```json
{
  "type": "deliberated",
  "classification": {
    "type": "deliberation",
    "requires_tools": false,
    "reasoning": "Requires multiple perspectives"
  },
  "stage1": {...},
  "stage2": {...},
  "stage3": {...},
  "metadata": {...}
}
```

## Testing

1. Test factual queries get direct responses
2. Test chat messages get direct responses  
3. Test deliberation queries go through full process
4. Test tool-requiring queries work with both paths
5. Test classification accuracy on edge cases

## Rollback Plan

If classification is inaccurate, add config option to force deliberation mode for all messages.

## Status

- [x] Proposal created
- [x] Proposal approved
- [x] Implementation started
- [x] Implementation complete
- [ ] Testing complete
- [ ] Merged to master
