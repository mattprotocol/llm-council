# Change Proposal 017: MCP Server Dynamic Port Assignment

## Summary
Run MCP servers by assigning port 15000 to the first server, incrementing by 1 for each additional server (15001, 15002, etc.) instead of using stdio-based communication.

## Motivation
- Current MCP servers use stdio which limits scalability and debugging
- HTTP-based servers allow better monitoring and external tool integration
- Predictable port assignment enables easier network configuration
- Enables parallel server management and health checks

## Detailed Design

### Port Assignment Logic
- Base port: 15000
- First server: 15000
- Second server: 15001
- Nth server: 15000 + (N-1)

### Configuration Updates
Update `mcp_servers.json` to optionally specify custom ports or use auto-assignment:

```json
{
  "base_port": 15000,
  "servers": [
    {
      "name": "calculator",
      "command": ["python3", "-m", "mcp_servers.calculator.server"],
      "port": null,  // null = auto-assign
      "description": "Basic math operations"
    }
  ]
}
```

### Implementation Requirements
1. Update `MCPClient` to support HTTP transport instead of/in addition to stdio
2. Modify `MCPRegistry.initialize()` to assign ports sequentially
3. Update MCP server templates to support HTTP mode
4. Add port tracking to registry status

### Server Communication
- Replace stdin/stdout with HTTP JSON-RPC endpoints
- Each server listens on assigned port
- Client makes HTTP POST requests for tool calls

## Testing Strategy
- Verify port assignment starts at 15000
- Test multiple servers get consecutive ports
- Validate HTTP communication with MCP protocol
- Test server restart with port recovery

## Impact Assessment
- **Backend**: Update MCP client/registry for HTTP transport
- **MCP Servers**: Add HTTP server wrapper
- **Configuration**: Extended mcp_servers.json schema
- **Network**: Requires ports 15000+ to be available
