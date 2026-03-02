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
   * Route a question to get suggested advisor panel.
   */
  async routeQuestion(councilId, question) {
    const response = await fetch(`/api/councils/${councilId}/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) throw new Error('Failed to route question');
    return response.json();
  },

  /**
   * Get full advisor roster for a council.
   */
  async getAdvisors(councilId) {
    const response = await fetch(`/api/councils/${councilId}/advisors`);
    if (!response.ok) throw new Error('Failed to get advisors');
    return response.json();
  },

  /**
   * Send a message with token-level streaming.
   * panelOverride: optional array of {advisor_id, model} to override routing.
   * executionMode: "chat" | "ranked" | "full"
   */
  async sendMessageStreamTokens(conversationId, content, onEvent, councilId = 'personal', panelOverride = null, forceDirect = false, executionMode = 'full') {
    const body = { content, council_id: councilId, execution_mode: executionMode };
    if (panelOverride) {
      body.panel_override = panelOverride;
    }
    if (forceDirect) {
      body.force_direct = true;
    }

    const response = await fetch(
      `/api/conversations/${conversationId}/message/stream-tokens`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
   * Get full models/config.
   */
  async getConfig() {
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error('Failed to get config');
    return response.json();
  },

  /**
   * Update models/config.
   */
  async updateConfig(data) {
    const response = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || 'Failed to update config');
    }
    return response.json();
  },

  /**
   * Export all configuration as JSON.
   */
  async exportConfig() {
    const response = await fetch('/api/config/export');
    if (!response.ok) throw new Error('Failed to export config');
    return response.json();
  },

  /**
   * Import configuration from JSON.
   */
  async importConfig(data) {
    const response = await fetch('/api/config/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || 'Failed to import config');
    }
    return response.json();
  },

  /**
   * Create a new council.
   */
  async createCouncil(data) {
    const response = await fetch('/api/councils', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || 'Failed to create council');
    }
    return response.json();
  },

  /**
   * Update an existing council.
   */
  async updateCouncil(councilId, data) {
    const response = await fetch(`/api/councils/${councilId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || 'Failed to update council');
    }
    return response.json();
  },

  /**
   * Delete a council.
   */
  async deleteCouncil(councilId) {
    const response = await fetch(`/api/councils/${councilId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || 'Failed to delete council');
    }
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
