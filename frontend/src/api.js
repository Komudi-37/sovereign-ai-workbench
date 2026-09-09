/**
 * API helper for Sovereign AI Workbench frontend.
 *
 * All backend communication goes through this module.
 * The frontend NEVER talks to Ollama directly.
 *
 * Flow: React → this module → FastAPI → LLMService → Ollama
 */

const API_BASE = "http://localhost:8000";

/**
 * Send a chat message to the backend and return the AI response.
 *
 * @param {string} message - The user's message.
 * @returns {Promise<{response: string, model: string}>} The AI response.
 * @throws {Error} With a user-friendly message if the request fails.
 */
export async function sendChatMessage(message) {
  let res;

  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
  } catch (err) {
    // Network error — backend is probably not running
    throw new Error(
      "Cannot connect to the backend server. Is FastAPI running on port 8000?"
    );
  }

  // Backend returned an error response
  if (!res.ok) {
    let detail = "Something went wrong.";
    try {
      const errorData = await res.json();
      detail = errorData.detail || detail;
    } catch {
      // Response wasn't JSON — use status text
      detail = `Server error: ${res.status} ${res.statusText}`;
    }
    throw new Error(detail);
  }

  return res.json();
}

/**
 * Check backend and Ollama health.
 *
 * @returns {Promise<{status: string, backend: string, ollama: string}>}
 */
export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    return res.json();
  } catch {
    return { status: "error", backend: "unavailable", ollama: "unknown" };
  }
}
