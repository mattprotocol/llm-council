#!/usr/bin/env python3
"""HTTP wrapper for MCP servers - provides HTTP JSON-RPC transport."""

import json
import argparse
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Callable


class MCPHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MCP JSON-RPC requests."""
    
    # Will be set by the server factory
    request_handler: Callable[[Dict[str, Any]], Dict[str, Any]] = None
    server_name: str = "mcp-server"
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_POST(self):
        """Handle POST requests containing JSON-RPC calls."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            request = json.loads(body)
            response = self.request_handler(request)
            
            if response is None:
                # Notification - return empty OK
                self.send_response(204)
                self.end_headers()
                return
            
            response_json = json.dumps(response)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(response_json))
            self.end_headers()
            self.wfile.write(response_json.encode())
            
        except json.JSONDecodeError as e:
            self._send_error(400, f"Invalid JSON: {e}")
        except Exception as e:
            self._send_error(500, str(e))
    
    def do_GET(self):
        """Handle GET requests - health check endpoint."""
        if self.path == '/health':
            response = json.dumps({"status": "ok", "server": self.server_name})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.end_headers()
            self.wfile.write(response.encode())
        else:
            self._send_error(404, "Not Found")
    
    def _send_error(self, code: int, message: str):
        """Send an error response."""
        response = json.dumps({"error": message})
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(response))
        self.end_headers()
        self.wfile.write(response.encode())


def run_http_server(
    port: int,
    request_handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    server_name: str = "mcp-server"
):
    """
    Run an MCP server with HTTP transport.
    
    Args:
        port: Port to listen on
        request_handler: Function to handle JSON-RPC requests
        server_name: Name of the server for logging
    """
    # Create handler class with the request handler attached
    handler_class = type(
        'MCPHandler',
        (MCPHTTPHandler,),
        {
            'request_handler': staticmethod(request_handler),
            'server_name': server_name
        }
    )
    
    server = HTTPServer(('127.0.0.1', port), handler_class)
    print(f"[{server_name}] HTTP server listening on port {port}", file=sys.stderr)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{server_name}] Shutting down...", file=sys.stderr)
        server.shutdown()


def get_port_from_args() -> int:
    """Parse command line arguments to get the port."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True, help='Port to listen on')
    args = parser.parse_args()
    return args.port


def stdio_main(request_handler: Callable[[Dict[str, Any]], Dict[str, Any]], server_name: str):
    """
    Run MCP server in stdio mode (original behavior) or HTTP mode.
    Automatically detects mode based on --port argument.
    """
    if '--port' in sys.argv:
        port = get_port_from_args()
        run_http_server(port, request_handler, server_name)
    else:
        # Original stdio mode
        print(f"[{server_name}] Starting in stdio mode...", file=sys.stderr)
        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
                response = request_handler(request)
                if response:
                    print(json.dumps(response), flush=True)
            except json.JSONDecodeError as e:
                print(f"[{server_name}] Invalid JSON: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[{server_name}] Error: {e}", file=sys.stderr)
