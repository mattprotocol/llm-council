#!/usr/bin/env python3
"""Calculator MCP server implementing basic math operations."""

import sys
import json
from typing import Dict, Any


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


# Tool definitions
TOOLS = [
    {
        "name": "add",
        "description": "Add two numbers together",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "subtract",
        "description": "Subtract the second number from the first",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "Number to subtract from"},
                "b": {"type": "number", "description": "Number to subtract"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "multiply",
        "description": "Multiply two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    },
    {
        "name": "divide",
        "description": "Divide the first number by the second",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "Dividend (number to divide)"},
                "b": {"type": "number", "description": "Divisor (number to divide by)"}
            },
            "required": ["a", "b"]
        }
    }
]


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle a JSON-RPC request."""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    response = {"jsonrpc": "2.0", "id": request_id}
    
    try:
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "calculator",
                    "version": "1.0.0"
                }
            }
        
        elif method == "notifications/initialized":
            # This is a notification, no response needed
            return None
        
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "add":
                result = add(arguments["a"], arguments["b"])
            elif tool_name == "subtract":
                result = subtract(arguments["a"], arguments["b"])
            elif tool_name == "multiply":
                result = multiply(arguments["a"], arguments["b"])
            elif tool_name == "divide":
                result = divide(arguments["a"], arguments["b"])
            else:
                response["error"] = {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}"
                }
                return response
            
            response["result"] = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "operation": tool_name,
                            "operands": {"a": arguments["a"], "b": arguments["b"]},
                            "result": result
                        })
                    }
                ]
            }
        
        else:
            response["error"] = {
                "code": -32601,
                "message": f"Unknown method: {method}"
            }
    
    except Exception as e:
        response["error"] = {
            "code": -32000,
            "message": str(e)
        }
    
    return response


def main():
    """Main entry point for the MCP server."""
    print("[Calculator MCP] Starting...", file=sys.stderr)
    
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            response = handle_request(request)
            
            if response:  # Don't respond to notifications
                print(json.dumps(response), flush=True)
        
        except json.JSONDecodeError as e:
            print(f"[Calculator MCP] Invalid JSON: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[Calculator MCP] Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
