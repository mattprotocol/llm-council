#!/usr/bin/env python3
"""Web Search MCP server for querying local search endpoint."""

import sys
import json
import urllib.request
import urllib.parse
import re
from typing import Dict, Any, List


def parse_html_results(html: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Parse search results from SearXNG HTML response.
    
    Args:
        html: Raw HTML response from SearXNG
        max_results: Maximum number of results to return
    
    Returns:
        List of result dicts with title, url, and snippet
    """
    results = []
    
    # Pattern to find result articles/divs
    # SearXNG uses <article class="result"> for each result
    result_pattern = re.compile(
        r'<article[^>]*class="[^"]*result[^"]*"[^>]*>.*?</article>',
        re.DOTALL | re.IGNORECASE
    )
    
    # Patterns to extract title, url, and snippet from each result
    # Title is in <h3><a href="...">Title text with <span class="highlight">words</span></a></h3>
    title_pattern = re.compile(r'<h3[^>]*>\s*<a[^>]*>(.+?)</a>\s*</h3>', re.DOTALL | re.IGNORECASE)
    url_pattern = re.compile(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"', re.DOTALL | re.IGNORECASE)
    snippet_pattern = re.compile(r'<p[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</p>', re.DOTALL | re.IGNORECASE)
    
    # Find all result blocks
    result_blocks = result_pattern.findall(html)
    
    for block in result_blocks[:max_results]:
        result = {}
        
        # Extract URL (from h3 > a href)
        url_match = url_pattern.search(block)
        if url_match:
            result['url'] = url_match.group(1)
        
        # Extract title (from h3 > a content, strip HTML tags)
        title_match = title_pattern.search(block)
        if title_match:
            title_html = title_match.group(1)
            # Remove HTML tags (like <span class="highlight">)
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            result['title'] = title
        
        # Extract snippet/content (strip HTML tags)
        snippet_match = snippet_pattern.search(block)
        if snippet_match:
            snippet_html = snippet_match.group(1)
            # Remove HTML tags and clean up
            snippet = re.sub(r'<[^>]+>', '', snippet_html).strip()
            # Normalize whitespace
            snippet = re.sub(r'\s+', ' ', snippet)
            result['snippet'] = snippet
        
        if result.get('title') or result.get('url'):
            results.append(result)
    
    return results


def search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Perform a web search using the local search endpoint.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (default 5)
    
    Returns:
        Search results dict with query, results list, and metadata
    """
    url = 'http://127.0.0.1:8080/search'
    # SearXNG requires POST with form data
    data = urllib.parse.urlencode({'q': query}).encode('utf-8')
    
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            
            # Try to parse as JSON first (in case SearXNG is configured for JSON)
            try:
                data = json.loads(content)
                return {
                    "success": True,
                    "query": query,
                    "results": data if isinstance(data, list) else [data],
                    "source": "local_search"
                }
            except json.JSONDecodeError:
                # Parse HTML response from SearXNG
                results = parse_html_results(content, max_results)
                if results:
                    return {
                        "success": True,
                        "query": query,
                        "results": results,
                        "source": "local_search"
                    }
                else:
                    # No results found
                    return {
                        "success": True,
                        "query": query,
                        "results": [],
                        "message": "No search results found",
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
