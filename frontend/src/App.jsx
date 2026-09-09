/**
 * Sovereign AI Workbench — Main Chat Application
 *
 * A clean ChatGPT-like interface that communicates with the local
 * FastAPI backend (which in turn talks to Ollama / qwen3:4b).
 *
 * Flow: User types message → api.js → FastAPI → LLMService → Ollama → qwen3:4b
 */

import { useState, useRef, useEffect } from "react";
import { sendChatMessage, checkHealth } from "./api";
import "./App.css";

function App() {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const [messages, setMessages] = useState([]);        // Chat history
  const [input, setInput] = useState("");               // Current input value
  const [isLoading, setIsLoading] = useState(false);    // Waiting for AI response
  const [error, setError] = useState(null);             // Error message to display
  const [backendStatus, setBackendStatus] = useState(null); // Health check result

  // Ref to auto-scroll chat to the bottom
  const chatEndRef = useRef(null);

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Check backend health on mount
  useEffect(() => {
    checkHealth().then(setBackendStatus);
  }, []);

  // Auto-scroll to the latest message
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  /** Send the user's message to the backend. */
  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    // Add user message to chat
    const userMessage = { role: "user", content: trimmed };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setError(null);
    setIsLoading(true);

    try {
      const data = await sendChatMessage(trimmed);

      // Add AI response to chat
      const aiMessage = { role: "assistant", content: data.response, model: data.model };
      setMessages((prev) => [...prev, aiMessage]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }

  /** Handle Enter key to send (Shift+Enter for newline). */
  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  /** Clear all messages from the chat. */
  function handleClear() {
    setMessages([]);
    setError(null);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="app">
      {/* ---- Header ---- */}
      <header className="header">
        <div className="header-left">
          <h1 className="header-title">Sovereign AI Workbench</h1>
          <span className="header-badge">Local AI · Offline Ready</span>
        </div>
        <div className="header-right">
          {backendStatus && (
            <span
              className={`status-dot ${
                backendStatus.ollama === "ok" ? "status-ok" : "status-error"
              }`}
              title={
                backendStatus.ollama === "ok"
                  ? "Ollama connected"
                  : "Ollama unavailable"
              }
            />
          )}
          <button
            className="clear-btn"
            onClick={handleClear}
            disabled={messages.length === 0}
            title="Clear conversation"
          >
            Clear Chat
          </button>
        </div>
      </header>

      {/* ---- Chat area ---- */}
      <main className="chat-area">
        {/* Empty state */}
        {messages.length === 0 && !isLoading && (
          <div className="empty-state">
            <div className="empty-icon">🔒</div>
            <h2>Welcome to Sovereign AI Workbench</h2>
            <p>
              Your messages are processed locally using <strong>Ollama</strong> and{" "}
              <strong>Qwen3 4B</strong>.
            </p>
            <p className="empty-hint">
              No data leaves your machine. Type a message below to get started.
            </p>
          </div>
        )}

        {/* Messages */}
        {messages.map((msg, i) => (
          <div key={i} className={`message message-${msg.role}`}>
            <div className="message-label">
              {msg.role === "user" ? "You" : "AI"}
              {msg.model && (
                <span className="message-model"> · {msg.model}</span>
              )}
            </div>
            <div className="message-content">{msg.content}</div>
          </div>
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div className="message message-assistant">
            <div className="message-label">AI</div>
            <div className="message-content thinking">
              <span className="dot-pulse" />
              Thinking…
            </div>
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="error-banner">
            <strong>Error:</strong> {error}
          </div>
        )}

        <div ref={chatEndRef} />
      </main>

      {/* ---- Input area ---- */}
      <footer className="input-area">
        <textarea
          className="message-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message… (Enter to send, Shift+Enter for new line)"
          rows={2}
          disabled={isLoading}
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
        >
          {isLoading ? "Sending…" : "Send"}
        </button>
      </footer>
    </div>
  );
}

export default App;
