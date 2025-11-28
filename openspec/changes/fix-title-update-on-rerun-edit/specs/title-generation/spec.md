## MODIFIED Requirements

### Requirement: Title Generation Trigger
The system SHALL generate a conversation title when:
1. A new message is sent to a conversation with a generic "Conversation <id>" title
2. A message is rerun (redo) in a conversation with a generic title
3. A message is edited in a conversation with a generic title

#### Scenario: Title generated on message rerun with generic title
- **WHEN** user reruns a message in a conversation with "Conversation <id>" title
- **THEN** title generation is triggered using the rerun message content
- **AND** the generic title is replaced with a meaningful title

#### Scenario: Title generated on message edit with generic title
- **WHEN** user edits a message in a conversation with "Conversation <id>" title
- **THEN** title generation is triggered using the edited message content
- **AND** the generic title is replaced with a meaningful title
