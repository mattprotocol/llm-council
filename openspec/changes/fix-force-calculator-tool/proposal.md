# Change: Force MCP Calculator Tool for Math Operations

## Why
When performing math calculations (e.g., `2+2` or `32442/783`), the system should use the MCP calculator tool when available, as it is faster and more accurate than LLM computation.

## What Changes
- Detect mathematical expressions in user queries
- Force routing to MCP calculator tool when available and capable
- Bypass LLM thinking for simple calculations

## Impact
- Affected specs: mcp-integration
- Affected code: `backend/council.py`, `backend/mcp_client.py`
