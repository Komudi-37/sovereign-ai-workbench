const API_BASE = 'http://localhost:8000';

async function fetchWithHandleError(url, options) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    return await res.json();
  } catch (error) {
    console.error(`Error fetching ${url}:`, error);
    throw error;
  }
}

export async function sendChatMessage(message, sessionId = null, documentIds = []) {
  return fetchWithHandleError(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId, document_ids: documentIds })
  });
}

export async function checkHealth() {
  return fetchWithHandleError(`${API_BASE}/api/health`, { method: 'GET' });
}

export async function getSecurityStatus() {
  return fetchWithHandleError(`${API_BASE}/api/security/status`, { method: 'GET' });
}

export async function getNetworkEvents(limit = 50) {
  return fetchWithHandleError(`${API_BASE}/api/security/network-events?limit=${limit}`, { method: 'GET' });
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  return fetchWithHandleError(`${API_BASE}/api/files/upload`, {
    method: 'POST',
    body: formData
  });
}

export async function listFiles() {
  return fetchWithHandleError(`${API_BASE}/api/files`, { method: 'GET' });
}

export async function getFile(id) {
  return fetchWithHandleError(`${API_BASE}/api/files/${id}`, { method: 'GET' });
}

export async function indexDocument(id) {
  return fetchWithHandleError(`${API_BASE}/api/documents/${id}/index`, { method: 'POST' });
}

export async function searchKnowledge(query, topK = 5) {
  return fetchWithHandleError(`${API_BASE}/api/rag/search?query=${encodeURIComponent(query)}&top_k=${topK}`, {
    method: 'POST'
  });
}

export async function runWorkflow({ workflow, message, documentIds, files, sessionId }) {
  return fetchWithHandleError(`${API_BASE}/api/workflows/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow, message, document_ids: documentIds, files, session_id: sessionId })
  });
}

export async function listWorkflows() {
  return fetchWithHandleError(`${API_BASE}/api/workflows`, { method: 'GET' });
}

export async function getWorkflow(id) {
  return fetchWithHandleError(`${API_BASE}/api/workflows/${id}`, { method: 'GET' });
}

export async function listArtifacts() {
  return fetchWithHandleError(`${API_BASE}/api/artifacts`, { method: 'GET' });
}

export async function getArtifact(id) {
  return fetchWithHandleError(`${API_BASE}/api/artifacts/${id}`, { method: 'GET' });
}

export async function downloadArtifact(id) {
  window.open(`${API_BASE}/api/artifacts/${id}/download`, '_blank');
}

export async function listAuditLogs() {
  return fetchWithHandleError(`${API_BASE}/api/audit`, { method: 'GET' });
}

export async function listSessions() {
  return fetchWithHandleError(`${API_BASE}/api/sessions`, { method: 'GET' });
}

export async function getSessionMessages(sessionId) {
  return fetchWithHandleError(`${API_BASE}/api/sessions/${sessionId}/messages`, { method: 'GET' });
}


export async function listConversations() {
  return fetchWithHandleError(`${API_BASE}/api/conversations`, { method: 'GET' });
}

export async function getConversation(conversationId) {
  return fetchWithHandleError(`${API_BASE}/api/conversations/${conversationId}`, { method: 'GET' });
}

export async function createConversation(title = 'New Chat') {
  return fetchWithHandleError(`${API_BASE}/api/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  });
}

export async function renameConversation(conversationId, title) {
  return fetchWithHandleError(`${API_BASE}/api/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  });
}

export async function deleteConversation(conversationId) {
  return fetchWithHandleError(`${API_BASE}/api/conversations/${conversationId}`, {
    method: 'DELETE'
  });
}
