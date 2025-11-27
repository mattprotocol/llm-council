"""MCP server registry for discovering and managing MCP servers."""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
from .client import MCPClient, MCPTool


class MCPRegistry:
    """Registry for managing MCP servers and their tools."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config()
        self.clients: Dict[str, MCPClient] = {}
        self.all_tools: Dict[str, MCPTool] = {}  # Full name -> tool
        self._initialized = False
    
    def _find_config(self) -> str:
        """Find the mcp_servers.json config file."""
        # Look in project root
        project_root = Path(__file__).parent.parent.parent
        return str(project_root / "mcp_servers.json")
    
    async def initialize(self) -> Dict[str, Any]:
        """Initialize all configured MCP servers and discover their tools."""
        if self._initialized:
            return self._get_status()
        
        # Load config
        if not os.path.exists(self.config_path):
            print(f"[MCP Registry] No config found at {self.config_path}, MCP disabled")
            self._initialized = True
            return {"enabled": False, "servers": [], "tools": []}
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"[MCP Registry] Failed to load config: {e}")
            self._initialized = True
            return {"enabled": False, "error": str(e)}
        
        servers = config.get("servers", [])
        if not servers:
            print("[MCP Registry] No servers configured")
            self._initialized = True
            return {"enabled": False, "servers": [], "tools": []}
        
        # Start each server
        project_root = Path(__file__).parent.parent.parent
        
        for server_config in servers:
            name = server_config["name"]
            command = server_config["command"]
            
            # Resolve command relative to project root
            if command and command[0] == "python":
                command[0] = "python3"
            
            client = MCPClient(
                server_name=name,
                command=command,
                cwd=str(project_root)
            )
            
            try:
                success = await client.start()
                if success:
                    self.clients[name] = client
                    # Add tools with full names
                    for tool_name, tool in client.tools.items():
                        full_name = f"{name}.{tool_name}"
                        self.all_tools[full_name] = tool
                    print(f"[MCP Registry] Started server: {name}")
                else:
                    print(f"[MCP Registry] Failed to start server: {name}")
            except Exception as e:
                print(f"[MCP Registry] Error starting {name}: {e}")
        
        self._initialized = True
        return self._get_status()
    
    async def shutdown(self):
        """Shutdown all MCP servers."""
        for name, client in self.clients.items():
            try:
                await client.stop()
                print(f"[MCP Registry] Stopped server: {name}")
            except Exception as e:
                print(f"[MCP Registry] Error stopping {name}: {e}")
        
        self.clients.clear()
        self.all_tools.clear()
        self._initialized = False
    
    def _get_status(self) -> Dict[str, Any]:
        """Get current registry status."""
        return {
            "enabled": len(self.clients) > 0,
            "servers": list(self.clients.keys()),
            "tools": list(self.all_tools.keys()),
            "tool_details": [
                {
                    "name": full_name,
                    "description": tool.description,
                    "server": tool.server_name
                }
                for full_name, tool in self.all_tools.items()
            ]
        }
    
    def get_all_tools_for_llm(self) -> List[Dict[str, Any]]:
        """Get all tool definitions in OpenAI function calling format."""
        tools = []
        for client in self.clients.values():
            tools.extend(client.get_tools_for_llm())
        return tools
    
    def get_tool_descriptions(self) -> str:
        """Get human-readable tool descriptions for prompts."""
        if not self.all_tools:
            return ""
        
        lines = ["Available tools:"]
        for full_name, tool in self.all_tools.items():
            schema = tool.input_schema
            params = schema.get("properties", {})
            param_str = ", ".join([
                f"{name}: {info.get('type', 'any')}"
                for name, info in params.items()
            ])
            lines.append(f"  - {full_name}({param_str}): {tool.description}")
        
        return "\n".join(lines)
    
    async def call_tool(self, full_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool by its full name (server.tool)."""
        if full_name not in self.all_tools:
            return {"error": f"Unknown tool: {full_name}"}
        
        tool = self.all_tools[full_name]
        client = self.clients.get(tool.server_name)
        
        if not client:
            return {"error": f"Server not running: {tool.server_name}"}
        
        try:
            result = await client.call_tool(tool.name, arguments)
            return {
                "success": True,
                "server": tool.server_name,
                "tool": tool.name,
                "input": arguments,
                "output": result
            }
        except Exception as e:
            return {
                "success": False,
                "server": tool.server_name,
                "tool": tool.name,
                "input": arguments,
                "error": str(e)
            }
    
    def should_use_tools(self, query: str) -> bool:
        """Determine if a query might benefit from tool use."""
        if not self.all_tools:
            return False
        
        # Simple heuristics for calculator
        math_indicators = [
            "calculate", "compute", "what is", "how much",
            "+", "-", "*", "/", "×", "÷", "plus", "minus",
            "times", "divided", "multiply", "add", "subtract",
            "sum", "difference", "product", "quotient"
        ]
        
        query_lower = query.lower()
        return any(ind in query_lower for ind in math_indicators)


# Singleton instance
_registry: Optional[MCPRegistry] = None


def get_mcp_registry() -> MCPRegistry:
    """Get the global MCP registry instance."""
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry


async def initialize_mcp() -> Dict[str, Any]:
    """Initialize the global MCP registry."""
    registry = get_mcp_registry()
    return await registry.initialize()


async def shutdown_mcp():
    """Shutdown the global MCP registry."""
    global _registry
    if _registry:
        await _registry.shutdown()
        _registry = None
