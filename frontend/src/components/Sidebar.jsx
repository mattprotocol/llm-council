import { useState } from 'react';
import './Sidebar.css';

export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  councilSelector,
  onShowLeaderboard,
}) {
  const [hoveredDeleteBtn, setHoveredDeleteBtn] = useState(null);

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1 className="sidebar-title">LLM Council</h1>
        <div className="sidebar-actions">
          <button className="new-chat-btn" onClick={onNewConversation} title="New conversation">
            + New
          </button>
          {onShowLeaderboard && (
            <button className="leaderboard-btn" onClick={onShowLeaderboard} title="Leaderboard">
              🏆
            </button>
          )}
        </div>
      </div>

      {councilSelector}

      <div className="conversation-list">
        {conversations.length === 0 ? (
          <div className="no-conversations">No conversations yet</div>
        ) : (
          conversations.map(conv => (
            <div
              key={conv.id}
              className={`conversation-item ${conv.id === currentConversationId ? 'active' : ''}`}
              onClick={() => onSelectConversation(conv.id)}
              onMouseEnter={() => setHoveredDeleteBtn(conv.id)}
              onMouseLeave={() => setHoveredDeleteBtn(null)}
            >
              <div className="conversation-info">
                <div className="conversation-title">{conv.title}</div>
                <div className="conversation-meta">
                  {conv.council_id && (
                    <span className="conversation-council">{conv.council_id}</span>
                  )}
                  <span className="conversation-messages">{conv.message_count || 0} msgs</span>
                </div>
              </div>
              {hoveredDeleteBtn === conv.id && (
                <button
                  className="delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteConversation(conv.id);
                  }}
                  title="Delete conversation"
                >
                  ×
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
