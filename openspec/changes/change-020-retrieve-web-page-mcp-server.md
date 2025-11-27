# Change Proposal 020: Retrieve Web Page MCP Server

## Summary
Add a new MCP server `retrieve-web-page` that fetches and returns HTML content from any URL.

## Motivation
- Enables LLMs to access current web content
- Foundation for other MCP servers that need web data
- Supports information retrieval from arbitrary sources
- Complements existing websearch server with full page retrieval

## Detailed Design

### Server Details
- **Name**: `retrieve-web-page`
- **Purpose**: Fetches and returns HTML content from a specified URL

### Tool: `get-page-from-url`

**Input Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `url` | string | Yes | The URL to fetch |

**Output:** String (HTML content of the page)

**Example:**
```json
// Input: {"url": "https://example.com"}
// Output: "<!DOCTYPE html><html>..."
```

### File Structure
```
mcp_servers/
  retrieve_web_page/
    __init__.py
    server.py
```

### Implementation
```python
import urllib.request
import urllib.error
from typing import Dict, Any

def get_page_from_url(url: str) -> Dict[str, Any]:
    """Fetch HTML content from a URL."""
    try:
        # Set a reasonable timeout and user agent
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; LLMCouncil/1.0)'}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8', errors='replace')
            return {
                "success": True,
                "url": url,
                "content": content,
                "status_code": response.status
            }
            
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "url": url,
            "error": f"HTTP Error {e.code}: {e.reason}"
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
```

### Tool Definition
```python
TOOLS = [
    {
        "name": "get-page-from-url",
        "description": "Returns the webpage's HTML content from the specified URL",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the webpage to retrieve"
                }
            },
            "required": ["url"]
        }
    }
]
```

### Configuration
Add to `mcp_servers.json`:
```json
{
  "name": "retrieve-web-page",
  "command": ["python3", "-m", "mcp_servers.retrieve_web_page.server"],
  "description": "Returns the webpage's HTML"
}
```

### Error Handling
- Network timeouts: 30 second timeout
- HTTP errors: Return status code and reason
- Invalid URLs: Return descriptive error
- Encoding issues: Use UTF-8 with error replacement

## Testing Strategy
- Test with valid URLs (example.com, etc.)
- Test error handling for invalid URLs
- Test timeout behavior
- Test encoding handling for non-UTF-8 pages
- Test redirect handling

## Impact Assessment
- **New Files**: `mcp_servers/retrieve_web_page/` directory
- **Configuration**: Add server to mcp_servers.json
- **Dependencies**: None (uses standard library)
- **Network**: Requires outbound HTTP access
