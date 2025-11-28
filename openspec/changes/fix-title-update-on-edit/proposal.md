# Change: Fix Title Update on Message Edit

## Why
When a message is edited (via edit button), the conversation title should be re-evaluated and updated if the edited content changes the conversation topic.

## What Changes
- Add title check trigger when message is edited
- Regenerate title based on edited message content
- Preserve existing title if topic remains similar

## Impact
- Affected specs: conversation-title
- Affected code: `frontend/src/App.jsx`, `frontend/src/components/ChatInterface.jsx`
