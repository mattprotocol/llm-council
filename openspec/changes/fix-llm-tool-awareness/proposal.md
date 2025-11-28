# Change: Fix LLM tool awareness and real-time data understanding

## Why
Models are refusing to provide current information even when MCP tools are available and have been executed. The model's thinking reveals it believes it "cannot access real-time data" despite the system providing tool results with current data. This is because the model's training data cutoff makes it think current dates are "in the future".

## What Changes
- Strengthen the system prompt to explicitly override training cutoff concerns
- Add explicit "tool output is REAL DATA" emphasis in prompts
- Pre-validate tool results before presenting to model
- Add post-processing to detect and retry refusal responses

## Impact
- Affected specs: mcp-tools
- Affected code: `backend/council.py` (check_and_execute_tools, chairman_direct_response, stage1_collect_responses_streaming)
