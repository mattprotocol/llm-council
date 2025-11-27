# Change Proposal 018: Intelligent MCP Tool Calling via Tool-Calling Model

## Summary
Before activating council members, use the configured `tool_calling` model to analyze queries and determine if MCP server capabilities should be invoked, then generate and execute appropriate tool calls.

## Motivation
- Current tool detection uses simple keyword matching (brittle, limited)
- LLM-based analysis provides intelligent context understanding
- Enables complex multi-step tool orchestration
- Uses dedicated lightweight model for efficiency

## Detailed Design

### Two-Phase Tool Calling Process

**Phase 1: Tool Analysis**
Prompt the `tool_calling` model with:
- User query (original or LLM-generated)
- Complete MCP server inventory:
  - Server name and general purpose
  - List of each server's tools/capabilities
  - Each tool's name, description, input parameters
  - Parameter names, descriptions, types, allowed values

The model outputs:
- Boolean: whether a tool should be used
- If yes: which server, which tool, reasoning

**Phase 2: Tool Execution**
If Phase 1 determines a tool is needed:
1. Generate detailed tool call prompt with:
   - Selected MCP server and tool details
   - Port number for communication
   - Input parameters with values extracted from query
2. Prompt `tool_calling` model to generate JSON for tool call
3. Execute tool call via MCP protocol
4. Return result as answer (or feed to council if synthesis needed)

### Tool Inventory Format
```json
{
  "servers": [
    {
      "name": "calculator",
      "purpose": "Basic math operations",
      "port": 15000,
      "tools": [
        {
          "name": "add",
          "description": "Add two numbers together",
          "parameters": [
            {"name": "a", "type": "number", "description": "First number", "required": true},
            {"name": "b", "type": "number", "description": "Second number", "required": true}
          ]
        }
      ]
    }
  ]
}
```

### System Prompts

**Phase 1 Analysis Prompt:**
```
You are a tool selection assistant. Analyze the user query and available tools.
Determine if any tool can help answer the query.

Available MCP Servers:
{tool_inventory}

User Query: {query}

Respond in JSON format:
{
  "use_tool": true/false,
  "server": "server_name" or null,
  "tool": "tool_name" or null,
  "reasoning": "brief explanation"
}
```

**Phase 2 Execution Prompt:**
```
Generate a tool call for the following:
Server: {server_name} (port {port})
Tool: {tool_name}
Description: {tool_description}
Parameters: {parameter_details}

User Query: {query}

Respond with JSON tool call:
{
  "server": "{server_name}",
  "tool": "{tool_name}",
  "arguments": { ... }
}
```

### Integration Point
Insert tool calling check at start of `run_council_session()`:
1. Build tool inventory from MCP registry
2. Run Phase 1 analysis
3. If tool needed, run Phase 2 and execute
4. If tool result is sufficient, return directly
5. Otherwise, proceed to normal council deliberation with tool result as context

## Testing Strategy
- Test with queries that clearly need tools (math, search)
- Test with queries that don't need tools
- Verify correct tool selection and parameter extraction
- Test multi-tool scenarios
- Benchmark response time vs keyword matching

## Impact Assessment
- **Backend**: New tool orchestration module, council.py integration
- **Configuration**: Uses existing `tool_calling` model from config.json
- **MCP Registry**: Add method to export full tool inventory
- **Performance**: Adds ~1-2 LLM calls before council for tool-relevant queries
