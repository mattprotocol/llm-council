# Change 017: Brevity System Prompt for Thinking Models

## Status
Implemented

## Problem
Thinking/reasoning models (like phi-4-mini-reasoning, apollo-thinking, jamba-reasoning) often produce extremely lengthy internal reasoning sessions, causing slow response times and sometimes partial outputs due to buffer limits.

## Solution
Add a system prompt that encourages concise, focused thinking while maintaining quality. This applies to all stages where thinking models are queried.

## Changes Required

### 1. backend/lmstudio.py
Add system prompt injection for thinking models:

```python
# Add helper function to detect thinking models
def is_thinking_model(model_id: str) -> bool:
    """Check if model is a thinking/reasoning model."""
    thinking_indicators = ['thinking', 'reasoning', 'o1', 'reason']
    return any(indicator in model_id.lower() for indicator in thinking_indicators)

# Add brevity system prompt constant
BREVITY_SYSTEM_PROMPT = """You are a focused, efficient assistant. When reasoning internally:
- Be concise and direct in your thinking
- Skip obvious steps - focus on key insights
- Limit internal deliberation to essential analysis
- Arrive at your answer quickly without excessive exploration
- If you find a good answer, commit to it rather than exploring alternatives"""
```

### 2. Modify query_model_streaming()
Prepend system message for thinking models:

```python
async def query_model_streaming(...):
    # Inject brevity prompt for thinking models
    if is_thinking_model(model):
        messages = [
            {"role": "system", "content": BREVITY_SYSTEM_PROMPT},
            *messages
        ]
    # ... rest of function
```

### 3. Modify query_model()
Same injection for non-streaming queries:

```python
async def query_model(...):
    # Inject brevity prompt for thinking models
    if is_thinking_model(model):
        messages = [
            {"role": "system", "content": BREVITY_SYSTEM_PROMPT},
            *messages
        ]
    # ... rest of function
```

## Testing
1. Submit a query and observe thinking token output
2. Compare thinking length before/after change
3. Verify response quality is maintained
4. Check that non-thinking models are unaffected

## Acceptance Criteria
- [ ] Thinking models produce shorter reasoning streams
- [ ] Response quality remains acceptable
- [ ] Non-thinking models work unchanged
- [ ] No timeout issues from lengthy thinking
