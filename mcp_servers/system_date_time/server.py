#!/usr/bin/env python3
"""System Date-Time MCP server for getting current date and time."""

import json
from datetime import datetime
from typing import Dict, Any


def get_system_date_time(return_type: str = "both") -> Dict[str, Any]:
    """Get current system date and/or time.
    
    Args:
        return_type: One of 'time', 'date', 'both', or 'unix'
    
    Returns:
        Dictionary with requested date/time information
    """
    now = datetime.now()
    
    if return_type == "time":
        return {
            "type": "time",
            "time": now.strftime("%H:%M:%S"),
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second
        }
    elif return_type == "date":
        return {
            "type": "date",
            "date": now.strftime("%Y-%m-%d"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "weekday": now.strftime("%A")
        }
    elif return_type == "unix":
        return {
            "type": "unix",
            "timestamp": int(now.timestamp()),
            "timestamp_ms": int(now.timestamp() * 1000)
        }
    else:  # "both" or default
        return {
            "type": "both",
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.strftime("%A"),
            "iso": now.isoformat()
        }


# Tool definitions
TOOLS = [
    {
        "name": "get-system-date-time",
        "description": "Get the current system date and/or time in various formats",
        "inputSchema": {
            "type": "object",
            "properties": {
                "return_type": {
                    "type": "string",
                    "description": "What to return: 'time' (current time only), 'date' (current date only), 'both' (date and time), or 'unix' (Unix timestamp)",
                    "enum": ["time", "date", "both", "unix"],
                    "default": "both"
                }
            },
            "required": []
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
                    "name": "system-date-time",
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
            
            if tool_name == "get-system-date-time":
                return_type = arguments.get("return_type", "both")
                result = get_system_date_time(return_type)
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
                        "text": json.dumps(result, indent=2)
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
    from mcp_servers.http_wrapper import stdio_main
    stdio_main(handle_request, "System Date-Time MCP")


if __name__ == "__main__":
    main()
