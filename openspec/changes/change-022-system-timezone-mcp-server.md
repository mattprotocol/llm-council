# Change Proposal 022: System Timezone MCP Server

## Summary
Add a new MCP server `system-timezone` that retrieves timezone information by using the `retrieve-web-page` MCP server to fetch data from whatismyip.com and Wikipedia's timezone database.

## Motivation
- Enables timezone-aware responses
- Provides comprehensive timezone database access
- Demonstrates multi-source data aggregation via MCP
- Useful for time conversion and scheduling queries

## Detailed Design

### Server Details
- **Name**: `system-timezone`
- **Purpose**: Returns timezone information from multiple sources

### Tool: `get-timezone-list`

**Input Parameters:** None

**Output:** String containing list of timezones from tz database

### Data Sources
1. **whatismyip.com** - For current system timezone based on IP
2. **Wikipedia** - For complete tz database timezone list (`https://en.wikipedia.org/wiki/List_of_tz_database_time_zones`)

### File Structure
```
mcp_servers/
  system_timezone/
    __init__.py
    server.py
```

### Implementation Strategy

**Step 1: Fetch System Timezone**
- Call `retrieve-web-page` with `https://www.whatismyip.com/`
- Parse timezone field from response

**Step 2: Fetch Timezone Database (optional)**
- Call `retrieve-web-page` with Wikipedia URL
- Parse timezone table from HTML
- Cache results (list rarely changes)

### HTML Parsing for Timezone Table
```python
import re
from typing import List, Dict

def parse_timezone_table(html: str) -> List[Dict[str, str]]:
    """Extract timezone entries from Wikipedia table."""
    timezones = []
    
    # Look for table rows with timezone data
    # Wikipedia uses <td> elements within timezone tables
    row_pattern = r'<tr[^>]*>.*?</tr>'
    rows = re.findall(row_pattern, html, re.DOTALL)
    
    for row in rows:
        # Extract timezone name (usually in first column)
        tz_match = re.search(r'>([A-Za-z_/]+)</a>', row)
        if tz_match:
            tz_name = tz_match.group(1)
            if '/' in tz_name:  # Valid tz format like "America/New_York"
                timezones.append({"timezone": tz_name})
    
    return timezones
```

### Tool Definition
```python
TOOLS = [
    {
        "name": "get-timezone-list",
        "description": "Returns list of time zones from the tz database",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]
```

### Configuration
Add to `mcp_servers.json`:
```json
{
  "name": "system-timezone",
  "command": ["python3", "-m", "mcp_servers.system_timezone.server"],
  "description": "Returns list of time zones",
  "depends_on": ["retrieve-web-page"]
}
```

### Response Format
```
System Timezone: America/Los_Angeles

Available Timezones:
- Africa/Abidjan
- Africa/Accra
- Africa/Addis_Ababa
- America/Adak
- America/Anchorage
- America/Anguilla
...
- Pacific/Wallis
```

### Caching Strategy
- Cache Wikipedia timezone list for 24 hours (data rarely changes)
- Always fetch fresh system timezone from whatismyip.com
- Store cache in memory (lost on server restart, acceptable)

## Testing Strategy
- Test timezone list parsing from Wikipedia HTML
- Test system timezone detection via whatismyip.com
- Verify cache behavior
- Test fallback when retrieve-web-page unavailable
- Test error handling for network failures

## Impact Assessment
- **New Files**: `mcp_servers/system_timezone/` directory
- **Configuration**: Add server to mcp_servers.json with dependency
- **Dependencies**: Requires `retrieve-web-page` MCP server
- **Network**: Requires outbound HTTP to whatismyip.com and Wikipedia
