# Change: Fix LLM Real-time Data Awareness

## Why
LLMs are not performing internet searches when asked for current news or weather. The thinking shows models believe 2025 is "in the future" from their training cutoff (2023), causing them to refuse providing real-time data instead of using available MCP tools.

## What Changes
- Strengthen system prompts to emphasize that the provided datetime IS the current real-world time
- Explicitly instruct models to use web search tools for ANY current/recent information
- Add explicit instruction that training cutoff dates are irrelevant when tools are available
- Modify tool selection prompts to mandate tool use for time-sensitive queries

## Impact
- Affected specs: mcp-integration
- Affected code: `backend/council.py`, `backend/prompts.py` or prompt constants
