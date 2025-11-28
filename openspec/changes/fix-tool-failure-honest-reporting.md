# Fix: Tool Failure Honest Reporting

## Summary
Update test validation to check for actual successful tool results (not just tool usage), and improve prompts to instruct models to report tool failures honestly instead of fabricating data.

## Problem
When a tool (e.g., websearch) is called but fails internally (returns `"success": false` in its output content), the test still passes because it only checks if the tool was *used*, not if it *succeeded*. Additionally, the model may fabricate news/data instead of honestly reporting the tool failure to the user.

## Solution

### 1. Test Validation Enhancement
Add `evaluate_tool_success()` method to `TestEvaluator` that checks:
- MCP-level success flag
- Content-level success (parses tool output JSON for `success: false` or `error` fields)

When `tool_used` is specified in expected behavior, also run `tool_success` check by default.

### 2. Prompt Updates
Update `format_tool_result_for_prompt()` to:
- Detect tool failures in the output content
- Format failure messages with clear instructions to be honest
- Include instructions to NOT fabricate data

Update `chairman_direct_response()` and `stage1_collect_responses_streaming()` to:
- Check if tool output failed using new `_tool_output_failed()` helper
- Use honest failure prompts when tool failed

## Files Changed
- `tests/test_runner.py` - Add `evaluate_tool_success()` and integrate with tool_used check
- `backend/council.py` - Add `_tool_output_failed()` helper, update prompts

## Testing
Run test scenario `current_news_websearch` - if websearch fails, test should now fail (not pass with fabricated data).
