## MODIFIED Requirements

### Requirement: Title Generation on Rerun
The system SHALL check if a conversation has a default title pattern when a message is re-run, and trigger title generation if detected.

#### Scenario: Rerun message with default title
- **WHEN** user reruns a message in a conversation
- **AND** the conversation title matches the default pattern `Conversation <id>`
- **THEN** the system triggers title generation
- **AND** updates the conversation title

#### Scenario: Rerun message with custom title
- **WHEN** user reruns a message in a conversation
- **AND** the conversation has a custom (non-default) title
- **THEN** the system does not regenerate the title
