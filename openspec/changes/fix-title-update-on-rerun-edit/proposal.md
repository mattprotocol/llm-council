# Change: Fix Title Update on Message Rerun and Edit

## Why
Conversations with generic `Conversation <id>` titles don't get updated when users rerun or edit messages. The title generation logic only triggers for completely new conversations, not when re-processing existing messages.

## What Changes
- Check for generic title AFTER truncation in rerun/edit scenarios
- Trigger title regeneration when conversation has generic title and user message exists
- Handle both `handleRedoMessage` (rerun) and `handleEditMessage` paths

## Impact
- Affected specs: title-generation
- Affected code: `backend/main.py` (streaming endpoint title logic)
