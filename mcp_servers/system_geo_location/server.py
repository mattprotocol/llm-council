#!/usr/bin/env python3
"""System Geo-Location MCP server for retrieving location based on IP."""

import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any


def get_page_from_url(url: str) -> str:
    """Fetch HTML content from a URL.
    
    Args:
        url: The URL to fetch
    
    Returns:
        HTML content as string, or empty string on error
    """
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; LLMCouncil/1.0)'}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8', errors='replace')
            
    except Exception:
        return ""


def parse_location_from_html(html: str) -> Dict[str, str]:
    """Extract location fields from whatismyip.com HTML.
    
    Args:
        html: HTML content from whatismyip.com
    
    Returns:
        Dictionary with city, state, postal, country fields
    """
    location = {}
    
    # whatismyip.com uses table rows with specific patterns
    patterns = {
        'city': r'City[:\s]*</[^>]+>\s*<[^>]+>([^<]+)',
        'state': r'(?:State|Region)[:\s]*</[^>]+>\s*<[^>]+>([^<]+)',
        'postal': r'(?:Postal|Zip)\s*(?:Code)?[:\s]*</[^>]+>\s*<[^>]+>([^<]+)',
        'country': r'Country[:\s]*</[^>]+>\s*<[^>]+>([^<]+)'
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            location[field] = match.group(1).strip()
    
    return location


def get_system_geo_location() -> Dict[str, Any]:
    """Get the system's geographic location based on IP.
    
    Returns:
        Dictionary with success status and location data or error
    """
    try:
        # Fetch the whatismyip.com page
        html = get_page_from_url("https://www.whatismyip.com/")
        
        if not html:
            return {
                "success": False,
                "error": "Failed to retrieve location page"
            }
        
        # Parse location from HTML
        location = parse_location_from_html(html)
        
        if not location:
            return {
                "success": False,
                "error": "Could not parse location from page"
            }
        
        # Format the result
        result_parts = []
        if location.get('city'):
            result_parts.append(f"City: {location['city']}")
        if location.get('state'):
            result_parts.append(f"State/Region: {location['state']}")
        if location.get('postal'):
            result_parts.append(f"Postal Code: {location['postal']}")
        if location.get('country'):
            result_parts.append(f"Country: {location['country']}")
        
        return {
            "success": True,
            "location": "\n".join(result_parts),
            "data": location
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Tool definitions
TOOLS = [
    {
        "name": "get-system-geo-location",
        "description": "Returns the system's geographic location (City, State/Region, Postal Code, Country) based on IP address",
        "inputSchema": {
            "type": "object",
            "properties": {},
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
                    "name": "system-geo-location",
                    "version": "1.0.0"
                }
            }
        
        elif method == "notifications/initialized":
            return None
        
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        
        elif method == "tools/call":
            tool_name = params.get("name")
            
            if tool_name == "get-system-geo-location":
                result = get_system_geo_location()
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
    stdio_main(handle_request, "System Geo-Location MCP")


if __name__ == "__main__":
    main()
