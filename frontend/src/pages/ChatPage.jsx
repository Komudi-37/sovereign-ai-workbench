import React, { useState, useRef, useEffect } from 'react';
import { Upload, Send, X, File, Cpu, Download, CheckCircle2, AlertCircle } from 'lucide-react';
import { sendChatMessage, uploadFile, runWorkflow } from '../api';

function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [sessionDocuments, setSessionDocuments] = useState([]);
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
      const filesArray = Array.from(e.target.files);
      setSelectedFiles((prev) => [...prev, ...filesArray]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const filesArray = Array.from(e.dataTransfer.files);
      setSelectedFiles((prev) => [...prev, ...filesArray]);
    }
  };

  const removeSelectedFile = (index) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() && selectedFiles.length === 0) return;

    const filesToUpload = [...selectedFiles];
    const userPrompt = input.trim();
    const attachedNames = filesToUpload.map(f => f.name);

    const userMessage = {
      role: 'user',
      content: userPrompt,
      files: attachedNames.length > 0 ? attachedNames : null
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setSelectedFiles([]);
    setLoading(true);

    try {
      let currentSessionId = sessionId;
      const uploadedDocIds = [];

      // Upload any new files
      for (const file of filesToUpload) {
        try {
          const uploadRes = await uploadFile(file);
          const docId = uploadRes.document_id || uploadRes.id || uploadRes.file_id;
          if (docId) {
            uploadedDocIds.push(docId);
            setSessionDocuments((prev) => [...prev, { id: docId, name: file.name }]);
          }
        } catch (uploadErr) {
          console.error(`Failed to upload ${file.name}:`, uploadErr);
        }
      }

      // Combine session documents + newly uploaded documents
      const allDocIds = Array.from(new Set([
        ...sessionDocuments.map(d => d.id),
        ...uploadedDocIds
      ]));

      // If documents are present, run multi-agent workflow
      if (allDocIds.length > 0) {
        const workflowRes = await runWorkflow({
          workflow: 'auto',
          message: userPrompt,
          documentIds: allDocIds,
          sessionId: currentSessionId
        });

        // Collect artifacts from workflow response
        let artifactsList = workflowRes.artifacts_details || [];
        if (artifactsList.length === 0 && workflowRes.artifacts) {
          artifactsList = workflowRes.artifacts.map((path, idx) => {
            const filename = path.split(/[\\/]/).pop();
            return {
              id: `art-${idx}`,
              filename,
              download_url: `/api/artifacts/download?path=${encodeURIComponent(path)}`
            };
          });
        }

        // Collect citations
        const ragData = workflowRes.agent_results?.rag?.data || {};
        const citationsList = (ragData.citations || []).map(cit => {
          if (typeof cit === 'string') {
            const clean = cit.replace(/^\[Source:\s*/, '').replace(/\]$/, '');
            const parts = clean.split(', page ');
            return { filename: parts[0] || cit, page: parts[1] || '1' };
          }
          return cit;
        });

        // Format assistant response content
        const wfName = workflowRes.workflow_name || 'Multi-Agent Workflow';
        const steps = workflowRes.steps || [];
        const reportData = workflowRes.agent_results?.report?.data || {};
        const isApproval = reportData.approval_status === 'pending_approval' || (reportData.approval_note);

        let assistantContent = `Completed execution of sovereign workflow '${wfName}'.`;
        if (isApproval) {
          assistantContent += `\n\nGenerated Formal Approval Note (Status: PENDING APPROVAL) with SOP-MAINT-001 guidance compliance and maintenance corrective actions.`;
        }

        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: assistantContent,
          workflowName: wfName,
          timeline: steps.map(s => ({
            label: `${(s.agent || '').toUpperCase()} Agent`,
            status: s.status || 'completed'
          })),
          citations: citationsList,
          artifacts: artifactsList
        }]);

        if (workflowRes.session_id) setSessionId(workflowRes.session_id);

      } else {
        // Direct local chat with Ollama
        const chatRes = await sendChatMessage(userPrompt, currentSessionId, []);
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: chatRes.response || chatRes.message,
          timeline: chatRes.timeline || [],
          citations: chatRes.citations || [],
          artifacts: chatRes.artifacts || []
        }]);
        if (chatRes.session_id) setSessionId(chatRes.session_id);
      }
    } catch (error) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `Error: ${error.message || 'Execution failed.'}`
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-page">
      <div className="messages-container">
        {messages.length === 0 && (
          <div className="empty-state text-center" style={{ padding: '40px 20px', color: 'var(--text-muted)' }}>
            <Cpu size={36} style={{ marginBottom: '12px', opacity: 0.6 }} />
            <h3 style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>Sovereign AI Workbench</h3>
            <p style={{ fontSize: '0.9rem', maxWidth: '540px', margin: '0 auto' }}>
              All processing is 100% on-premise. Attach inspection reports or SOP documents to execute automated multi-agent analysis, RAG guidance retrieval, and formal approval note generation.
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`message ${msg.role}`}>
            {msg.role === 'assistant' && (
              <div className="message-header">
                <Cpu size={14} /> <span>qwen3:4b &middot; Sovereign Local AI</span>
                {msg.workflowName && <span className="status-badge success" style={{ marginLeft: '8px', fontSize: '0.7rem' }}>{msg.workflowName}</span>}
              </div>
            )}
            <div className="message-content">
              {msg.files && msg.files.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
                  {msg.files.map((fname, fi) => (
                    <div key={fi} className="attached-file">
                      <File size={14} /> {fname}
                    </div>
                  ))}
                </div>
              )}

              {msg.content}
              
              {msg.timeline && msg.timeline.length > 0 && (
                <div className="timeline">
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                    Agent Execution Sequence
                  </div>
                  {msg.timeline.map((item, i) => (
                    <div key={i} className="timeline-item">
                      <CheckCircle2 size={14} style={{ color: item.status === 'completed' ? 'var(--success)' : 'var(--warning)' }} />
                      <span>{item.label}</span>
                      <span className="status-badge" style={{ marginLeft: 'auto', fontSize: '0.65rem' }}>{item.status}</span>
                    </div>
                  ))}
                </div>
              )}

              {msg.citations && msg.citations.length > 0 && (
                <div className="citations">
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                    Knowledge Base Citations
                  </div>
                  {msg.citations.map((cit, i) => (
                    <div key={i} className="citation">
                      [Source: {cit.filename}, page {cit.page || 1}]
                    </div>
                  ))}
                </div>
              )}

              {msg.artifacts && msg.artifacts.length > 0 && (
                <div className="artifacts">
                  <div style={{ width: '100%', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                    Generated Artifacts
                  </div>
                  {msg.artifacts.map((art, i) => {
                    const downloadHref = art.download_url
                      ? `http://localhost:8000${art.download_url}`
                      : `http://localhost:8000/api/artifacts/${art.id}/download`;
                    return (
                      <a key={i} href={downloadHref} target="_blank" rel="noreferrer" className="artifact-link">
                        <Download size={14} style={{ marginRight: '6px' }} />
                        Download {art.filename}
                      </a>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="message assistant loading">
            <div className="message-header">
              <Cpu size={14} /> <span>Local agents are processing...</span>
            </div>
            <div className="message-content" style={{ color: 'var(--text-muted)' }}>
              Executing local pipeline (OCR &rarr; Local RAG &rarr; Report Generation)...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="input-area" onSubmit={handleSubmit} onDragOver={handleDragOver} onDrop={handleDrop}>
        {selectedFiles.length > 0 && (
          <div style={{ position: 'absolute', top: '-42px', left: 0, display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {selectedFiles.map((file, fIndex) => (
              <div key={fIndex} className="file-chip">
                <File size={14} />
                <span>{file.name}</span>
                <button type="button" onClick={() => removeSelectedFile(fIndex)}><X size={14} /></button>
              </div>
            ))}
          </div>
        )}
        <div className="input-row">
          <input
            type="file"
            multiple
            ref={fileInputRef}
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <button
            type="button"
            className="icon-btn"
            title="Attach local documents (PDF, TXT, CSV, images)"
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={20} />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Analyze inspection documents, query SOP standards, generate approval note..."
            disabled={loading}
          />
          <button
            type="submit"
            className="icon-btn primary"
            disabled={loading || (!input.trim() && selectedFiles.length === 0)}
          >
            <Send size={20} />
          </button>
        </div>
      </form>
    </div>
  );
}

export default ChatPage;
