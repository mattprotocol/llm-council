/**
 * API client for the LLM Council backend.
 * Uses relative URLs (proxied via Vite in dev, same-origin in prod).
 */

export const api = {
  /**
   * List available councils.
   */
  async listCouncils() {
    const response = await fetch('/api/councils');
    if (!response.ok) throw new Error('Failed to list councils');
    return response.json();
  },

  /**
   * List conversations, optionally filtered by council.
   */
  async listConversations(councilId = null) {
    const params = councilId ? `?council_id=${councilId}` : '';
    const response = await fetch(`/api/conversations${params}`);
    if (!response.ok) throw new Error('Failed to list conversations');
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation(councilId = 'personal') {
    const response = await fetch('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ council_id: councilId }),
    });
    if (!response.ok) throw new Error('Failed to create conversation');
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(`/api/conversations/${conversationId}`);
    if (!response.ok) throw new Error('Failed to get conversation');
    return response.json();
  },

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId, councilId = 'personal') {
    const response = await fetch(`/api/conversations/${conversationId}?council_id=${councilId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete conversation');
    return response.json();
  },

  /**
   * Send a message with token-level streaming.
   */
  async sendMessageStreamTokens(conversationId, content, onEvent, councilId = 'personal') {
    const response = await fetch(
      `/api/conversations/${conversationId}/message/stream-tokens`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, council_id: councilId }),
      }
    );

    if (!response.ok) throw new Error('Failed to send message');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6));
            onEvent(event.type, event);
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
          }
        }
      }
    }

    if (buffer.startsWith('data: ')) {
      try {
        const event = JSON.parse(buffer.slice(6));
        onEvent(event.type, event);
      } catch (e) { /* ignore */ }
    }
  },

  /**
   * Get leaderboard data.
   */
  async getLeaderboard(councilId = null) {
    const url = councilId ? `/api/leaderboard/${councilId}` : '/api/leaderboard';
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to get leaderboard');
    return response.json();
  },

  /**
   * Health check.
   */
  async healthCheck() {
    const response = await fetch('/api/health');
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
  },
};
