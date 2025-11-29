## ADDED Requirements

### Requirement: Memory Recording
The system SHALL record all messages to the Graphiti knowledge graph during both council deliberation and direct answer workflows.

#### Scenario: User message recording
- **WHEN** a user sends a message to the council
- **THEN** the system records the message as an episode to Graphiti
- **AND** the episode includes source="llm_council", source_description="user"
- **AND** recording happens asynchronously without blocking the response

#### Scenario: Council member response recording
- **WHEN** a council member generates a response in Stage 1
- **THEN** the system records the response as an episode to Graphiti
- **AND** the episode includes the model name in source_description
- **AND** recording happens after the response is complete

#### Scenario: Chairman synthesis recording
- **WHEN** the chairman generates a final synthesis in Stage 3
- **THEN** the system records the synthesis as an episode to Graphiti
- **AND** the episode includes source_description="chairman:{model_name}"

#### Scenario: Direct response recording
- **WHEN** a direct response is generated (non-deliberation path)
- **THEN** the system records both the query and response to Graphiti

### Requirement: Memory-Based Response Confidence
The system SHALL evaluate whether stored memories can answer a query with sufficient confidence.

#### Scenario: High confidence memory response
- **WHEN** a user query is received
- **AND** related memories are found in Graphiti
- **AND** the confidence score exceeds the configured threshold
- **THEN** the system uses the memory to generate a response
- **AND** the standard LLM/tool workflow is bypassed

#### Scenario: Low confidence fallback
- **WHEN** a user query is received
- **AND** memory confidence is below the threshold
- **THEN** the system proceeds with the standard workflow (tool check, routing, etc.)

#### Scenario: Memory recency weighting
- **WHEN** calculating confidence for a memory
- **THEN** the system weights confidence based on memory age
- **AND** older memories receive lower confidence scores
- **AND** the max_memory_age_days config controls the age cutoff

### Requirement: Confidence Model Configuration
The system SHALL support configurable confidence scoring via config.json.

#### Scenario: Custom confidence model
- **WHEN** a confidence model is specified in config.json
- **THEN** that model is used for memory confidence scoring

#### Scenario: Fallback to chairman model
- **WHEN** the confidence model ID is empty in config.json
- **THEN** the chairman model is used for confidence scoring

#### Scenario: Configurable threshold
- **WHEN** a memory confidence threshold is specified in config.json
- **THEN** that threshold determines the cutoff for memory-based responses

### Requirement: Graceful Degradation
The system SHALL continue functioning normally if Graphiti is unavailable.

#### Scenario: Graphiti unavailable on startup
- **WHEN** the Graphiti MCP server is not reachable during initialization
- **THEN** the system logs a warning
- **AND** memory features are disabled
- **AND** standard workflow continues without memory checks

#### Scenario: Graphiti fails during operation
- **WHEN** a Graphiti call fails during message recording or retrieval
- **THEN** the system logs the error
- **AND** continues with the standard workflow
- **AND** does not return an error to the user
