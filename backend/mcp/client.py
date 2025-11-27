"""MCP client for communicating with MCP servers via stdio."""

import asyncio
import json
import sys
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class MCPTool:
    """Represents an MCP tool/capability."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


class MCPClient:
    """Client for communicating with an MCP server via stdio."""
    
    def __init__(self, server_name: str, command: List[str], cwd: Optional[str] = None):
        self.server_name = server_name
        self.command = command
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: Dict[str, MCPTool] = {}
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
    
    async def start(self) -> bool:
        """Start the MCP server process and initialize connection."""
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd
            )
            
            # Start reading responses
            self._read_task = asyncio.create_task(self._read_responses())
            
            # Initialize the connection
            await self._initialize()
            
            # Discover tools
            await self._discover_tools()
            
            return True
            
        except Exception as e:
            print(f"[MCP] Failed to start server {self.server_name}: {e}")
            return False
    
    async def stop(self):
        """Stop the MCP server process."""
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
    
    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        self._request_id += 1
        request_id = self._request_id
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        
        # Send request
        request_json = json.dumps(request) + "\n"
        self.process.stdin.write(request_json.encode())
        await self.process.stdin.drain()
        
        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            return response
        except asyncio.TimeoutError:
            del self._pending_requests[request_id]
            raise TimeoutError(f"MCP request {method} timed out")
    
    async def _read_responses(self):
        """Continuously read responses from the MCP server."""
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                try:
                    response = json.loads(line.decode())
                    request_id = response.get("id")
                    
                    if request_id and request_id in self._pending_requests:
                        future = self._pending_requests.pop(request_id)
                        if "error" in response:
                            future.set_exception(Exception(response["error"].get("message", "Unknown error")))
                        else:
                            future.set_result(response.get("result", {}))
                
                except json.JSONDecodeError:
                    continue
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[MCP] Error reading from {self.server_name}: {e}")
    
    async def _initialize(self):
        """Initialize the MCP connection."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "llm-council",
                "version": "0.6.0"
            }
        })
        
        # Send initialized notification
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self.process.stdin.write((json.dumps(notification) + "\n").encode())
        await self.process.stdin.drain()
        
        return result
    
    async def _discover_tools(self):
        """Discover available tools from the MCP server."""
        result = await self._send_request("tools/list")
        
        tools = result.get("tools", [])
        for tool_data in tools:
            tool = MCPTool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
                server_name=self.server_name
            )
            self.tools[tool.name] = tool
        
        print(f"[MCP] Discovered {len(self.tools)} tools from {self.server_name}: {list(self.tools.keys())}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the MCP server."""
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        return result
    
    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """Get tool definitions in OpenAI function calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": f"{self.server_name}.{tool.name}",
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }
            for tool in self.tools.values()
        ]
