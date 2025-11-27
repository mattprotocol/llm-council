#!/usr/bin/env python3
"""Web Search MCP server for querying local search endpoint."""

import sys
import json
import urllib.request
import urllib.parse
from typing import Dict, Any


def search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Perform a web search using the local search endpoint.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (default 5)
    
    Returns:
        Search results dict with query, results list, and metadata
    """
    # URL encode the query
    encoded_query = urllib.parse.quote(query)
    url = f'http://127.0.0.1:8080?q="{encoded_query}"'
    
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read().decode('utf-8')
            
            # Try to parse as JSON
            try:
                data = json.loads(content)
                return {
                    "success": True,
                    "query": query,
                    "results": data if isinstance(data, list) else [data],
                    "source": "local_search"
                }
            except json.JSONDecodeError:
                # Return raw text if not JSON
                return {
                    "success": True,
                    "query": query,
                    "results": [{"text": content[:2000]}],  # Limit length
                    "source": "local_search"
                }
                
    except urllib.error.URLError as e:
        return {
            "success": False,
            "query": query,
            "error": f"Search endpoint unavailable: {str(e)}",
            "source": "local_search"
        }
    except Exception as e:
        return {
            "success": False,
            "query": query,
            "error": str(e),
            "source": "local_search"
        }


# Tool definitions
TOOLS = [
    {
        "name": "search",
        "description": "Search the web for current information. Use for time-sensitive topics, recent events, specific entities, or when you need up-to-date information.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query - be specific and include relevant keywords"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
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
                    "name": "websearch",
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
            
            if tool_name == "search":
                query = arguments.get("query", "")
                max_results = arguments.get("max_results", 5)
                result = search(query, max_results)
                
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
                    "message": f"Unknown tool: {tool_name}"
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
    stdio_main(handle_request, "WebSearch MCP")


if __name__ == "__main__":
    main()
