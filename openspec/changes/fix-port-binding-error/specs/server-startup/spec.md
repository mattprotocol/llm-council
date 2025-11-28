## ADDED Requirements

### Requirement: Port Availability Check
The startup script SHALL check if backend port (8001) and frontend port (5173) are already in use before attempting to start servers.

#### Scenario: Port in use - automatic cleanup
- **WHEN** start.sh is executed and port 8001 or 5173 is in use
- **THEN** the script SHALL kill the existing process on that port and proceed with startup

#### Scenario: Ports available
- **WHEN** start.sh is executed and no process is using ports 8001 or 5173
- **THEN** the script SHALL start servers normally without any cleanup
