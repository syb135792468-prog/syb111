/**
 * frontend/api.js - 统一接口请求封装（含认证支持）
 */
const api = {
    // ==================== 认证接口 ====================
    async register(username, password) {
        const resp = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        return resp.json();
    },

    async login(username, password) {
        const resp = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        return resp.json();
    },

    async me() {
        const resp = await fetch(`${API_BASE}/auth/me`, {
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    // ==================== 聊天接口 ====================
    health() {
        return fetch(`${API_BASE}/health`);
    },

    chatStream(message, signal, conversationId) {
        const body = { message };
        if (conversationId) body.conversation_id = conversationId;
        return fetch(`${API_BASE}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getToken()}`,
            },
            body: JSON.stringify(body),
            signal: signal,
        });
    },

    async chatHistory(limit = 100, conversationId) {
        let url = `${API_BASE}/chat/history?limit=${limit}`;
        if (conversationId) url += `&conversation_id=${conversationId}`;
        const resp = await fetch(url, {
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    async clearHistory() {
        const resp = await fetch(`${API_BASE}/chat/history`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    // ==================== 对话会话接口 ====================
    async listConversations() {
        const resp = await fetch(`${API_BASE}/conversation`, {
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    async createConversation(title) {
        const resp = await fetch(`${API_BASE}/conversation`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getToken()}`,
            },
            body: JSON.stringify({ title: title || null }),
        });
        return resp.json();
    },

    async getConversation(conversationId) {
        const resp = await fetch(`${API_BASE}/conversation/${conversationId}`, {
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    async deleteConversation(conversationId) {
        const resp = await fetch(`${API_BASE}/conversation/${conversationId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    // ==================== 其他接口 ====================
    async loadProfile() {
        const resp = await fetch(`${API_BASE}/profile/${USER_ID}`, {
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    async loadResources(resourceType) {
        let url = `${API_BASE}/resource/?user_id=${USER_ID}&limit=${DEFAULT_RESOURCE_FETCH_LIMIT}`;
        if (resourceType) url += `&resource_type=${resourceType}`;
        const resp = await fetch(url, {
            headers: { 'Authorization': `Bearer ${getToken()}` },
        });
        return resp.json();
    },

    async generateResource(topic, resourceType) {
        const resp = await fetch(`${API_BASE}/resource/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getToken()}`,
            },
            body: JSON.stringify({
                user_id: USER_ID,
                topic: topic,
                resource_type: resourceType,
            }),
        });
        return resp.json();
    },

    generateMindmap(topic) {
        return this.generateResource(topic, 'mindmap');
    },
};

// ==================== Token 管理 ====================
const TOKEN_KEY = 'auth_token';
const USERNAME_KEY = 'auth_username';

function getToken() {
    return localStorage.getItem(TOKEN_KEY) || '';
}

function setToken(token, username) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, username);
}

function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
}

function getStoredUsername() {
    return localStorage.getItem(USERNAME_KEY) || '';
}
