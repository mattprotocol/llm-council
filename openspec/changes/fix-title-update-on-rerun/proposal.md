# Change: Fix Title Update on App Start/Message Rerun

## Why
When starting the app or re-running a message/query, conversations with the default title `Conversation <message_id>` are not being updated to a meaningful title.

## What Changes
- Check for default title pattern on message rerun
- Trigger title generation when default title is detected
- Ensure title updates on app startup if needed

## Impact
- Affected specs: conversation-title
- Affected code: `frontend/src/App.jsx`, `backend/council.py`
