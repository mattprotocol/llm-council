# Change: Fix port binding error on startup

## Why
When running `start.sh`, if a previous server instance is still running on port 8001, the startup fails with "ERROR: [Errno 48] error while attempting to bind on address ('0.0.0.0', 8001): address already in use". Users must manually find and kill the process.

## What Changes
- Add automatic detection and cleanup of stale processes on port 8001 before starting server
- Update `start.sh` to check if port is in use and offer to kill existing process
- Add graceful startup with port availability check

## Impact
- Affected specs: server-startup (new capability)
- Affected code: `start.sh`
