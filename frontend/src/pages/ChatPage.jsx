import React, { useState, useRef, useEffect } from 'react';
import { Upload, Send, X, File, Cpu } from 'lucide-react';
import { sendChatMessage, uploadFile, runWorkflow } from '../api';

function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() && !selectedFile) return;

    const userMessage = {
      role: 'user',
      content: input,
      file: selectedFile ? selectedFile.name : null
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      let fileId = null;
      let currentSessionId = sessionId;

      if (selectedFile) {
        const uploadRes = await uploadFile(selectedFile);
        fileId = uploadRes.file_id || uploadRes.id; // Adjust based on actual API
        setSelectedFile(null);
      }

      if (fileId) {
        const workflowRes = await runWorkflow({
          workflow: 'auto',
          message: userMessage.content,
          files: [fileId],
          sessionId: currentSessionId
        });
        
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: workflowRes.message || 'Workflow executed.',
          timeline: workflowRes.timeline || [],
          citations: workflowRes.citations || [],
          artifacts: workflowRes.artifacts || []
        }]);
        if (workflowRes.session_id) setSessionId(workflowRes.session_id);
      } else {
        const chatRes = await sendChatMessage(userMessage.content, currentSessionId);
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: chatRes.message || chatRes.response,
          citations: chatRes.citations || [],
          artifacts: chatRes.artifacts || []
        }]);
        if (chatRes.session_id) setSessionId(chatRes.session_id);
      }
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${error.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-page">
      <div className="messages-container">
        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            {msg.role === 'assistant' && (
              <div className="message-header">
                <Cpu size={14} /> <span>qwen3:4b &middot; Local</span>
              </div>
            )}
            <div className="message-content">
              {msg.file && (
                <div className="attached-file">
                  <File size={16} /> {msg.file}
                </div>
              )}
              {msg.content}
              
              {msg.timeline && msg.timeline.length > 0 && (
                <div className="timeline">
                  {msg.timeline.map((item, i) => (
                    <div key={i} className="timeline-item">
                      {item.status === 'completed' ? '✓' : '●'} {item.label}
                    </div>
                  ))}
                </div>
              )}

              {msg.citations && msg.citations.length > 0 && (
                <div className="citations">
                  {msg.citations.map((cit, i) => (
                    <span key={i} className="citation">[Source: {cit.filename}, page {cit.page}]</span>
                  ))}
                </div>
              )}

              {msg.artifacts && msg.artifacts.length > 0 && (
                <div className="artifacts">
                  {msg.artifacts.map((art, i) => (
                    <a key={i} href={`http://localhost:8000/api/artifacts/${art.id}/download`} target="_blank" rel="noreferrer" className="artifact-link">
                      Download {art.filename}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="message assistant loading">Local model is processing...</div>}
        <div ref={messagesEndRef} />
      </div>

      <form className="input-area" onSubmit={handleSubmit} onDragOver={handleDragOver} onDrop={handleDrop}>
        {selectedFile && (
          <div className="file-chip">
            <File size={14} />
            <span>{selectedFile.name}</span>
            <button type="button" onClick={() => setSelectedFile(null)}><X size={14} /></button>
          </div>
        )}
        <div className="input-row">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <button type="button" className="icon-btn" onClick={() => fileInputRef.current?.click()}>
            <Upload size={20} />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Send a message or drop a file..."
            disabled={loading}
          />
          <button type="submit" className="icon-btn primary" disabled={loading || (!input.trim() && !selectedFile)}>
            <Send size={20} />
          </button>
        </div>
      </form>
    </div>
  );
}

export default ChatPage;
