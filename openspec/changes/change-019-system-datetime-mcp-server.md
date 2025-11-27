# Change Proposal 019: System Date-Time MCP Server

## Summary
Add a new MCP server `system-date-time` that provides system date and time information in various formats.

## Motivation
- LLMs don't have access to current date/time
- Useful for time-sensitive queries
- Simple implementation demonstrates MCP server pattern
- Foundation for time-based calculations

## Detailed Design

### Server Details
- **Name**: `system-date-time`
- **Purpose**: Returns the system's date and/or time in configurable formats

### Tool: `get-system-date-time`

**Input Parameters:**
| Name | Type | Required | Description | Default |
|------|------|----------|-------------|---------|
| `return-type` | integer | No | Format selector | 3 |

**Return Type Values:**
- `1` = Time only in 24h format: `HH:MM:SS`
- `2` = Date only: `MM-DD-YYYY`
- `3` = Both date and time (default)
- `4` = Unix timestamp in milliseconds

**Output:** String

**Examples:**
```json
// Input: {"return-type": 1}
// Output: "15:30:45"

// Input: {"return-type": 2}
// Output: "11-27-2025"

// Input: {"return-type": 3}
// Output: "11-27-2025 15:30:45"

// Input: {"return-type": 4}
// Output: "1732722645000"
```

### File Structure
```
mcp_servers/
  system_date_time/
    __init__.py
    server.py
```

### Implementation
```python
import time
from datetime import datetime

def get_system_date_time(return_type: int = 3) -> str:
    now = datetime.now()
    
    if return_type == 1:
        return now.strftime("%H:%M:%S")
    elif return_type == 2:
        return now.strftime("%m-%d-%Y")
    elif return_type == 3:
        return now.strftime("%m-%d-%Y %H:%M:%S")
    elif return_type == 4:
        return str(int(time.time() * 1000))
    else:
        return now.strftime("%m-%d-%Y %H:%M:%S")
```

### Configuration
Add to `mcp_servers.json`:
```json
{
  "name": "system-date-time",
  "command": ["python3", "-m", "mcp_servers.system_date_time.server"],
  "description": "Returns the system's date as month-day-year, and/or time in 24h format as hours:minutes:seconds, or unix date-time in milliseconds"
}
```

## Testing Strategy
- Test each return-type value
- Verify format correctness
- Test default value behavior
- Test invalid return-type handling

## Impact Assessment
- **New Files**: `mcp_servers/system_date_time/` directory
- **Configuration**: Add server to mcp_servers.json
- **Dependencies**: None (uses standard library)
