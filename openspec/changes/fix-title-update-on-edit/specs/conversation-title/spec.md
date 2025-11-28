## MODIFIED Requirements

### Requirement: Title Generation on Message Edit
The system SHALL regenerate the conversation title when a message is edited, ensuring the title reflects the updated content.

#### Scenario: Edit message triggers title update
- **WHEN** user edits a message using the edit button
- **THEN** the system triggers title generation based on edited content
- **AND** updates the conversation title accordingly

#### Scenario: Edit preserves meaningful title context
- **WHEN** user makes a minor edit that doesn't change the topic
- **THEN** the system still regenerates the title based on the edited content
