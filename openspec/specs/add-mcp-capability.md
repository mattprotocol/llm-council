# OpenSpec: Add MCP Capability

**Status:** `implemented`
**Created:** 2025-01-27
**Version:** v0.6.0

## Summary

Add Model Context Protocol (MCP) capability to enable extensible functionality through external tool servers. Test with a calculator MCP server that handles basic math questions.

## Motivation

MCP provides a standardized way to extend LLM capabilities with external tools. This enables:
- Easy addition of new capabilities without modifying core code
- Standardized tool discovery and invocation
- Clear separation between LLM reasoning and tool execution

## Specification

### Components

1. **MCP Client Module** (`backend/mcp/`)
   - `client.py`: MCP client for connecting to tool servers
   - `registry.py`: Discovers and registers available MCP servers/tools at startup
   - `__init__.py`: Module exports

2. **Calculator MCP Server** (`mcp_servers/calculator/`)
   - Simple MCP server implementing basic math operations
   - Operations: add, subtract, multiply, divide
   - Returns result with operation details

3. **Integration**
   - On app start, discover all MCP server capabilities
   - Store tool schemas for function calling
   - When processing queries, include tool definitions
   - Display MCP server name, capability used, input/output in response

### MCP Server Configuration

Add `mcp_servers.json` configuration:
```json
{
  "servers": [
    {
      "name": "calculator",
      "command": ["python", "-m", "mcp_servers.calculator"],
      "description": "Basic math operations"
    }
  ]
}
```

### Output Format

When MCP tool is used, display:
```
🔧 MCP Tool Used: calculator.add
   Input: {"a": 5, "b": 3}
   Output: {"result": 8}
```

## Implementation Plan

1. Create MCP client infrastructure
2. Create calculator MCP server
3. Integrate tool discovery at startup
4. Modify council to support tool calls
5. Add UI display for tool usage

## Files to Modify/Create

- Create: `backend/mcp/__init__.py`
- Create: `backend/mcp/client.py`
- Create: `backend/mcp/registry.py`
- Create: `mcp_servers/__init__.py`
- Create: `mcp_servers/calculator/__init__.py`
- Create: `mcp_servers/calculator/server.py`
- Create: `mcp_servers.json`
- Modify: `backend/main.py` (startup tool discovery)
- Modify: `backend/council.py` (tool integration)
- Modify: `frontend/src/components/Stage1.jsx` (tool display)

## Acceptance Criteria

- [ ] MCP servers discovered at app startup
- [ ] Calculator server responds to basic math queries
- [ ] Tool usage displayed with server name, capability, input/output
- [ ] Non-math queries work without tool invocation
