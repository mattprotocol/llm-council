"""MCP client for communicating with MCP servers via stdio or HTTP."""

import asyncio
import json
import sys
import urllib.request
import urllib.error
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
    """Client for communicating with an MCP server via stdio or HTTP."""
    
    def __init__(self, server_name: str, command: List[str], cwd: Optional[str] = None, 
                 port: Optional[int] = None, external_url: Optional[str] = None):
        self.server_name = server_name
        self.command = command
        self.cwd = cwd
        self.port = port  # If set, use HTTP transport
        self.external_url = external_url  # If set, connect to external server (no subprocess)
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: Dict[str, MCPTool] = {}
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._session_id: Optional[str] = None  # For stateful HTTP MCP servers
    
    @property
    def _use_http(self) -> bool:
        """Check if using HTTP transport."""
        return self.port is not None or self.external_url is not None
    
    @property
    def _is_external(self) -> bool:
        """Check if connecting to external server (no subprocess needed)."""
        return self.external_url is not None
    
    @property
    def _http_url(self) -> str:
        """Get the HTTP URL for the server."""
        if self.external_url:
            return self.external_url.rstrip('/')
        return f"http://127.0.0.1:{self.port}"
    
    async def start(self) -> bool:
        """Start the MCP server process and initialize connection."""
        try:
            if self._is_external:
                # External server - just verify it's reachable
                await self._wait_for_http_ready()
            elif self._use_http:
                # Start server with --port argument
                cmd = self.command + ['--port', str(self.port)]
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.cwd
                )
                
                # Wait for server to be ready
                await self._wait_for_http_ready()
            else:
                # Original stdio mode
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
    
    async def _wait_for_http_ready(self, timeout: float = 10.0, interval: float = 0.1):
        """Wait for the HTTP server to be ready."""
        import time
        start = time.time()
        
        # For external servers, try the base URL's health endpoint
        # For local servers, append /health to the URL
        if self._is_external:
            # External URL might be like http://localhost:8000/mcp/
            # Try the base URL with /health
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(self.external_url.rstrip('/'))
            health_url = urlunparse((parsed.scheme, parsed.netloc, '/health', '', '', ''))
        else:
            health_url = f"{self._http_url}/health"
        
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(health_url, headers={'Accept': '*/*'})
                with urllib.request.urlopen(req, timeout=1) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, ConnectionRefusedError):
                pass
            await asyncio.sleep(interval)
        
        raise TimeoutError(f"HTTP server {self.server_name} did not start within {timeout}s")
    
    async def stop(self):
        """Stop the MCP server process."""
        # External servers are not managed by us
        if self._is_external:
            return
            
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
        
        if self._use_http:
            return await self._send_http_request(request)
        else:
            return await self._send_stdio_request(request, request_id)
    
    async def _send_http_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request via HTTP."""
        request_json = json.dumps(request).encode('utf-8')
        is_notification = 'id' not in request  # Notifications don't have id
        
        def do_request():
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream'
            }
            # Include session ID if we have one
            if self._session_id:
                headers['mcp-session-id'] = self._session_id
            
            req = urllib.request.Request(
                self._http_url,
                data=request_json,
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                # Store session ID from response if present
                session_id = response.headers.get('mcp-session-id')
                
                # 204 No Content = notification response (empty)
                if response.status == 204:
                    return {'_session_id': session_id, '_empty': True}
                
                content = response.read().decode('utf-8')
                
                # Empty response for notifications is valid
                if not content.strip():
                    return {'_session_id': session_id, '_empty': True}
                
                # Check if it's SSE format (event: ... data: ...)
                if content.startswith('event:') or content.startswith('data:'):
                    # Parse SSE format - extract JSON from data lines
                    for line in content.split('\n'):
                        if line.startswith('data:'):
                            json_str = line[5:].strip()
                            if json_str:
                                result = json.loads(json_str)
                                result['_session_id'] = session_id
                                return result
                    return {'_session_id': session_id, '_empty': True}
                else:
                    # Regular JSON response
                    result = json.loads(content)
                    if isinstance(result, dict):
                        result['_session_id'] = session_id
                    return result
        
        # Run in thread pool to not block async loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, do_request)
        
        # Update session ID if received
        if isinstance(response, dict):
            new_session = response.pop('_session_id', None)
            if new_session:
                self._session_id = new_session
            # Handle empty responses for notifications
            if response.pop('_empty', False):
                return {}
        
        if isinstance(response, dict) and "error" in response:
            raise Exception(response["error"].get("message", "Unknown error"))
        
        return response.get("result", {}) if isinstance(response, dict) else {}
    
    async def _send_stdio_request(self, request: Dict[str, Any], request_id: int) -> Dict[str, Any]:
        """Send a request via stdio."""
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
            raise TimeoutError(f"MCP request {request['method']} timed out")
    
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
        if self._use_http:
            # Send via HTTP
            notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await self._send_http_request(notification)
        else:
            # Send via stdio
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
