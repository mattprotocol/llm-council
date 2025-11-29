#!/usr/bin/env python3
"""Firecrawl MCP server for web scraping and content extraction using Firecrawl API."""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

# Firecrawl API configuration
FIRECRAWL_API_KEY = "fc-08c737edff4d41a2bb372810f9a76f40"
FIRECRAWL_API_BASE = "https://api.firecrawl.dev/v1"


def scrape_url(url: str, formats: list = None, only_main_content: bool = True) -> Dict[str, Any]:
    """Scrape a URL using Firecrawl API.
    
    Args:
        url: The URL to scrape
        formats: Output formats (default: ["markdown"])
        only_main_content: Whether to extract only main content (default: True)
    
    Returns:
        Dictionary with success status and scraped content
    """
    if formats is None:
        formats = ["markdown"]
    
    try:
        # Build request payload
        payload = {
            "url": url,
            "formats": formats,
            "onlyMainContent": only_main_content
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            f"{FIRECRAWL_API_BASE}/scrape",
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {FIRECRAWL_API_KEY}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        if result.get('success'):
            content_data = result.get('data', {})
            return {
                "success": True,
                "url": url,
                "markdown": content_data.get('markdown', ''),
                "title": content_data.get('metadata', {}).get('title', ''),
                "description": content_data.get('metadata', {}).get('description', ''),
                "source_url": content_data.get('metadata', {}).get('sourceURL', url)
            }
        else:
            return {
                "success": False,
                "url": url,
                "error": result.get('error', 'Unknown error from Firecrawl API')
            }
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        return {
            "success": False,
            "url": url,
            "error": f"HTTP Error {e.code}: {error_body[:200]}"
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "url": url,
            "error": f"URL Error: {str(e.reason)}"
        }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e)
        }


def batch_scrape_urls(urls: list, formats: list = None, only_main_content: bool = True) -> Dict[str, Any]:
    """Scrape multiple URLs using Firecrawl API.
    
    Args:
        urls: List of URLs to scrape
        formats: Output formats (default: ["markdown"])
        only_main_content: Whether to extract only main content (default: True)
    
    Returns:
        Dictionary with success status and list of scraped results
    """
    results = []
    for url in urls[:10]:  # Limit to 10 URLs
        result = scrape_url(url, formats, only_main_content)
        results.append(result)
    
    return {
        "success": True,
        "total": len(results),
        "successful": sum(1 for r in results if r.get('success')),
        "results": results
    }


# Tool definitions
TOOLS = [
    {
        "name": "firecrawl-scrape",
        "description": "Scrape a web page and extract its content as clean markdown using Firecrawl. Best for extracting readable content from articles, blogs, and documentation pages.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to scrape"
                },
                "only_main_content": {
                    "type": "boolean",
                    "description": "If true, extracts only the main content (excludes headers, footers, navigation). Default: true",
                    "default": True
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "firecrawl-batch-scrape",
        "description": "Scrape multiple web pages and extract their content as clean markdown. Useful for gathering information from multiple sources. Limited to 10 URLs per call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of URLs to scrape (max 10)"
                },
                "only_main_content": {
                    "type": "boolean",
                    "description": "If true, extracts only the main content. Default: true",
                    "default": True
                }
            },
            "required": ["urls"]
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
                    "name": "firecrawl",
                    "version": "1.0.0"
                }
            }
        
        elif method == "notifications/initialized":
            return None
        
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "firecrawl-scrape":
                url = arguments.get("url")
                only_main = arguments.get("only_main_content", True)
                result = scrape_url(url, ["markdown"], only_main)
                
                # Format output for readability
                if result.get("success"):
                    output = f"Title: {result.get('title', 'N/A')}\n"
                    output += f"URL: {result.get('source_url', url)}\n"
                    if result.get('description'):
                        output += f"Description: {result['description']}\n"
                    output += f"\n--- Content ---\n\n{result.get('markdown', '')}"
                else:
                    output = f"Error scraping {url}: {result.get('error', 'Unknown error')}"
                
            elif tool_name == "firecrawl-batch-scrape":
                urls = arguments.get("urls", [])
                only_main = arguments.get("only_main_content", True)
                result = batch_scrape_urls(urls, ["markdown"], only_main)
                
                # Format output
                output_parts = [f"Scraped {result['successful']}/{result['total']} URLs:\n"]
                for r in result.get('results', []):
                    if r.get('success'):
                        output_parts.append(f"\n### {r.get('title', 'Untitled')} ({r.get('url')})\n")
                        # Truncate content for batch results
                        content = r.get('markdown', '')[:2000]
                        if len(r.get('markdown', '')) > 2000:
                            content += "\n... (truncated)"
                        output_parts.append(content)
                    else:
                        output_parts.append(f"\n### Error: {r.get('url')}\n{r.get('error')}\n")
                
                output = '\n'.join(output_parts)
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
                        "text": output
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
    stdio_main(handle_request, "Firecrawl MCP")


if __name__ == "__main__":
    main()
