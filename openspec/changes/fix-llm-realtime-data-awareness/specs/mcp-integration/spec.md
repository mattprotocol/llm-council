## MODIFIED Requirements

### Requirement: Real-time Data Awareness
The system SHALL ensure LLMs understand that the provided system datetime is the current real-world time and that they MUST use available MCP tools (web search, datetime, weather) for any queries about current or recent information, regardless of their training data cutoff.

#### Scenario: Current news query uses web search
- **WHEN** user asks for today's news or current events
- **AND** web search MCP tool is available
- **THEN** the system instructs LLM to use web search tool
- **AND** the LLM does NOT refuse based on training cutoff
- **AND** returns real-time search results

#### Scenario: Current weather query uses appropriate tool
- **WHEN** user asks for current weather
- **AND** relevant MCP tools are available (geolocation, web search)
- **THEN** the system instructs LLM to use available tools
- **AND** the LLM does NOT claim inability due to training cutoff

#### Scenario: System prompt emphasizes datetime reality
- **WHEN** system prompt is constructed
- **THEN** it explicitly states the provided datetime IS the current real-world time
- **AND** instructs LLM that training cutoff is irrelevant for tool-assisted queries
