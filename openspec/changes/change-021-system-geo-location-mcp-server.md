# Change Proposal 021: System Geo-Location MCP Server

## Summary
Add a new MCP server `system-geo-location` that retrieves the system's geographic location by using the `retrieve-web-page` MCP server to fetch data from whatismyip.com.

## Motivation
- Enables location-aware responses
- Demonstrates MCP server-to-server communication
- Useful for timezone, weather, and local information queries
- Provides geographic context without requiring API keys

## Detailed Design

### Server Details
- **Name**: `system-geo-location`
- **Purpose**: Returns the system's geographic location based on IP

### Tool: `get-system-geo-location`

**Input Parameters:** None

**Output:** String containing:
- City
- State/Region
- Postal Code
- Country

**Example Output:**
```
City: San Francisco
State/Region: California
Postal Code: 94102
Country: United States
```

### Dependencies
- Requires `retrieve-web-page` MCP server to be running
- Uses whatismyip.com for IP-based geolocation

### File Structure
```
mcp_servers/
  system_geo_location/
    __init__.py
    server.py
```

### Implementation Strategy
1. Call `retrieve-web-page` server's `get-page-from-url` tool with `https://www.whatismyip.com/`
2. Parse HTML response to extract location fields
3. Format and return location string

### HTML Parsing
The whatismyip.com page contains location information in identifiable HTML elements. Parse using regex or simple string matching:

```python
import re

def parse_location_from_html(html: str) -> dict:
    """Extract location fields from whatismyip.com HTML."""
    location = {}
    
    # Look for location fields in the HTML
    patterns = {
        'city': r'City[:\s]*</[^>]+>\s*<[^>]+>([^<]+)',
        'state': r'State/Region[:\s]*</[^>]+>\s*<[^>]+>([^<]+)',
        'postal': r'Postal Code[:\s]*</[^>]+>\s*<[^>]+>([^<]+)',
        'country': r'Country[:\s]*</[^>]+>\s*<[^>]+>([^<]+)'
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            location[field] = match.group(1).strip()
    
    return location
```

### MCP Server Communication
```python
import json
import urllib.request

async def call_retrieve_web_page(url: str) -> str:
    """Call the retrieve-web-page MCP server."""
    # Assumes retrieve-web-page is running on its assigned port
    # This will need to integrate with the MCP registry to get the correct port
    
    # Alternative: Direct HTTP call if using HTTP transport
    # Or: Internal Python import if both servers are in same process
    pass
```

### Configuration
Add to `mcp_servers.json`:
```json
{
  "name": "system-geo-location",
  "command": ["python3", "-m", "mcp_servers.system_geo_location.server"],
  "description": "Returns the system's geographic location",
  "depends_on": ["retrieve-web-page"]
}
```

### Tool Definition
```python
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
```

## Testing Strategy
- Test with network access to whatismyip.com
- Verify HTML parsing extracts correct fields
- Test fallback when retrieve-web-page unavailable
- Test error handling for network failures

## Impact Assessment
- **New Files**: `mcp_servers/system_geo_location/` directory
- **Configuration**: Add server to mcp_servers.json with dependency
- **Dependencies**: Requires `retrieve-web-page` MCP server
- **Network**: Requires outbound HTTP access to whatismyip.com
