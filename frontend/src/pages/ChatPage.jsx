import React, { useState, useRef, useEffect } from 'react';
import {
  Upload, Send, X, File, FileText, Cpu, Download, CheckCircle2,
  AlertCircle, Terminal, Code, Play, Compass, GitBranch, ArrowRight,
  Eye, BarChart3, FileSpreadsheet, Presentation, Plus, MessageSquare,
  Edit2, Trash2, Check, Search, Shield
} from 'lucide-react';
import {
  sendChatMessage, uploadFile, runWorkflow,
  listConversations, getConversation, createConversation,
  renameConversation, deleteConversation
} from '../api';

function ChatPage() {
  const [conversations, setConversations] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [chatSearch, setChatSearch] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [sessionDocuments, setSessionDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingChatId, setEditingChatId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async (preferredId = null) => {
    try {
      const list = await listConversations();
      setConversations(list || []);

      const savedId = preferredId || localStorage.getItem('sovereign_active_chat_id');
      const targetChat = list.find(c => c.id === savedId) || (list.length > 0 ? list[0] : null);

      if (targetChat) {
        selectConversation(targetChat.id);
      } else if (list.length === 0) {
        handleNewChat();
      }
    } catch (err) {
      console.error('Failed to load conversations:', err);
    }
  };

  const selectConversation = async (convId) => {
    setActiveChatId(convId);
    localStorage.setItem('sovereign_active_chat_id', convId);
    try {
      const conv = await getConversation(convId);
      if (conv && conv.messages) {
        setMessages(conv.messages.map(m => ({
          role: m.role,
          content: m.content,
          files: m.files || null,
          workflowName: m.workflowName || m.workflow_name || null,
          timeline: m.timeline || [],
          citations: m.citations || [],
          artifacts: m.artifacts || [],
          coding: m.coding || null,
          vision: m.vision || null,
          dataAnalysis: m.dataAnalysis || m.data_analysis || null,
          executionPlan: m.executionPlan || m.execution_plan || null,
        })));
      } else {
        setMessages([]);
      }
      setSelectedFiles([]);
    } catch (err) {
      console.error(`Failed to load conversation ${convId}:`, err);
    }
  };

  const handleNewChat = async () => {
    try {
      const newChat = await createConversation('New Chat');
      if (newChat && newChat.id) {
        setConversations(prev => [newChat, ...prev.filter(c => c.id !== newChat.id)]);
        setActiveChatId(newChat.id);
        localStorage.setItem('sovereign_active_chat_id', newChat.id);
        setMessages([]);
        setSelectedFiles([]);
        setSessionDocuments([]);
      }
    } catch (err) {
      console.error('Failed to create new conversation:', err);
    }
  };

  const handleRename = async (convId, e) => {
    e.stopPropagation();
    if (!editTitle.trim()) {
      setEditingChatId(null);
      return;
    }
    try {
      const updated = await renameConversation(convId, editTitle.trim());
      setConversations(prev => prev.map(c => c.id === convId ? { ...c, title: updated.title } : c));
      setEditingChatId(null);
    } catch (err) {
      console.error(`Failed to rename conversation ${convId}:`, err);
    }
  };

  const handleDelete = async (convId, e) => {
    e.stopPropagation();
    try {
      await deleteConversation(convId);
      const remaining = conversations.filter(c => c.id !== convId);
      setConversations(remaining);
      if (activeChatId === convId) {
        if (remaining.length > 0) {
          selectConversation(remaining[0].id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error(`Failed to delete conversation ${convId}:`, err);
    }
  };

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
      let currentSessionId = activeChatId;
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
              filename: filename || `Artifact_${idx + 1}`,
              download_url: `/api/artifacts/download?path=${encodeURIComponent(path)}`
            };
          });
        }

        // Collect rich citations with snippet text
        const ragData = workflowRes.agent_results?.rag?.data || {};
        const ragResults = ragData.results || [];
        const rawCitations = ragData.citations || [];

        const citationsList = [];
        const seenCitKeys = new Set();

        for (const item of ragResults) {
          const doc = item.document || 'Document';
          const page = item.page || 1;
          const text = (item.text || '').trim();
          const key = `${doc}__p${page}__${text.slice(0, 80)}`;
          if (!seenCitKeys.has(key)) {
            seenCitKeys.add(key);
            citationsList.push({
              filename: doc,
              page,
              text,
              citation: item.citation || `[Source: ${doc}, page ${page}]`
            });
          }
        }

        // Fallback to raw string citations if ragResults is empty
        if (citationsList.length === 0 && rawCitations.length > 0) {
          for (const cit of rawCitations) {
            if (typeof cit === 'string') {
              const clean = cit.replace(/^\[Source:\s*/, '').replace(/\]$/, '');
              const parts = clean.split(', page ');
              const doc = parts[0] || cit;
              const page = parts[1] || '1';
              const key = `${doc}__p${page}`;
              if (!seenCitKeys.has(key)) {
                seenCitKeys.add(key);
                citationsList.push({ filename: doc, page, text: '', citation: cit });
              }
            }
          }
        }

        // Format assistant response content
        const wfName = workflowRes.workflow_name || 'Multi-Agent Workflow';
        const steps = workflowRes.steps || [];
        const reportData = workflowRes.agent_results?.report?.data || {};
        const isApproval = reportData.approval_status === 'pending_approval' || (reportData.approval_note);

        let assistantContent = `Completed execution of sovereign workflow '${wfName}'.`;
        if (isApproval) {
          assistantContent += `\n\nGenerated Formal Approval Note (Status: PENDING APPROVAL) with SOP-MAINT-001 guidance compliance and maintenance corrective actions.`;
        }

        const codingData = workflowRes.agent_results?.coding?.data || null;
        const dataAnalysisData = workflowRes.agent_results?.data_analysis?.data || null;
        const executionPlan = workflowRes.execution_plan || null;

        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: assistantContent,
          workflowName: wfName,
          timeline: steps.map(s => ({
            label: `${(s.agent || '').toUpperCase()} Agent`,
            status: s.status || 'completed'
          })),
          citations: citationsList,
          artifacts: artifactsList,
          coding: codingData,
          dataAnalysis: dataAnalysisData,
          executionPlan: executionPlan
        }]);

        if (workflowRes.session_id && workflowRes.session_id !== activeChatId) {
          setActiveChatId(workflowRes.session_id);
          localStorage.setItem('sovereign_active_chat_id', workflowRes.session_id);
        }

      } else {
        // Direct local chat with Ollama
        const chatRes = await sendChatMessage(userPrompt, currentSessionId, []);
        const returnedId = chatRes.session_id || chatRes.conversation_id;
        if (returnedId && returnedId !== activeChatId) {
          setActiveChatId(returnedId);
          localStorage.setItem('sovereign_active_chat_id', returnedId);
        }

        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: chatRes.response || chatRes.message,
          timeline: chatRes.timeline || [],
          citations: chatRes.citations || [],
          artifacts: chatRes.artifacts || [],
          coding: chatRes.coding || null,
          vision: chatRes.vision || null,
          dataAnalysis: chatRes.data_analysis || null,
          executionPlan: chatRes.execution_plan || null
        }]);
      }

      // Refresh conversations list to update title & timestamp
      const updatedList = await listConversations();
      setConversations(updatedList || []);
    } catch (error) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `Error: ${error.message || 'Execution failed.'}`
      }]);
    } finally {
      setLoading(false);
    }
  };

  // Helper to group citations by filename and categorize into SOP vs Inspection Report
  const groupCitationsBySource = (citations) => {
    if (!citations || citations.length === 0) return [];
    const groups = {};

    citations.forEach((c) => {
      const fn = c.filename || 'Document';
      if (!groups[fn]) {
        const fnLower = fn.toLowerCase();
        let category = 'general';
        let categoryLabel = 'Reference Document';

        if (fnLower.includes('sop') || fnLower.includes('standard') || fnLower.includes('proc')) {
          category = 'sop';
          categoryLabel = 'Standard Operating Procedure (SOP)';
        } else if (fnLower.includes('insp') || fnLower.includes('report') || fnLower.includes('finding')) {
          category = 'report';
          categoryLabel = 'Inspection Evidence';
        }

        groups[fn] = {
          filename: fn,
          category,
          categoryLabel,
          items: []
        };
      }
      groups[fn].items.push(c);
    });

    return Object.values(groups);
  };

  // Helper to determine file icon and category for artifacts
  const getArtifactMeta = (filename) => {
    const fn = (filename || '').toLowerCase();
    const ext = fn.split('.').pop();
    const isApproval = fn.includes('approval_note') || fn.includes('approval');

    if (ext === 'docx') {
      return { ext: 'DOCX', type: 'docx', isApproval, isProminent: true };
    }
    if (ext === 'pdf') {
      return { ext: 'PDF', type: 'pdf', isApproval, isProminent: true };
    }
    if (ext === 'xlsx') {
      return { ext: 'XLSX', type: 'xlsx', isApproval, isProminent: true };
    }
    if (ext === 'pptx') {
      return { ext: 'PPTX', type: 'pptx', isApproval, isProminent: true };
    }
    if (ext === 'csv') {
      return { ext: 'CSV', type: 'data', isApproval: false, isProminent: false };
    }
    return { ext: ext ? ext.toUpperCase() : 'FILE', type: 'json', isApproval: false, isProminent: false };
  };

  const filteredConversations = conversations.filter(c =>
    (c.title || 'Untitled Chat').toLowerCase().includes(chatSearch.toLowerCase())
  );

  return (
    <div className="chat-container-layout">
      {/* Persistent ChatGPT-style Left Sidebar */}
      <aside className="chat-history-sidebar">
        <div className="chat-history-header">
          <button className="new-chat-btn" onClick={handleNewChat}>
            <Plus size={16} />
            <span>New Chat</span>
          </button>
          <div className="chat-search-wrap">
            <Search size={14} className="chat-search-icon" />
            <input
              type="text"
              className="chat-search-input"
              placeholder="Search conversations..."
              value={chatSearch}
              onChange={(e) => setChatSearch(e.target.value)}
            />
            {chatSearch && (
              <button className="chat-search-clear" onClick={() => setChatSearch('')} title="Clear search">
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        <div className="chat-history-list">
          {filteredConversations.length === 0 && (
            <div className="chat-history-empty">
              {chatSearch ? 'No matching conversations' : 'No conversations yet'}
            </div>
          )}
          {filteredConversations.map((conv) => {
            const isActive = conv.id === activeChatId;
            const isEditing = editingChatId === conv.id;

            return (
              <div
                key={conv.id}
                className={`chat-history-item ${isActive ? 'active' : ''}`}
                onClick={() => selectConversation(conv.id)}
              >
                <div className="chat-item-main">
                  <MessageSquare size={14} style={{ flexShrink: 0 }} />
                  {isEditing ? (
                    <input
                      type="text"
                      className="chat-rename-input"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRename(conv.id, e);
                        if (e.key === 'Escape') setEditingChatId(null);
                      }}
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <div className="chat-item-info">
                      <span className="chat-item-title" title={conv.title}>
                        {conv.title || 'Untitled Chat'}
                      </span>
                      <span className="chat-item-date">
                        {conv.updated_at ? new Date(conv.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                      </span>
                    </div>
                  )}
                </div>

                <div className="chat-item-actions">
                  {isEditing ? (
                    <button
                      className="chat-action-btn"
                      title="Save title"
                      onClick={(e) => handleRename(conv.id, e)}
                    >
                      <Check size={13} />
                    </button>
                  ) : (
                    <>
                      <button
                        className="chat-action-btn"
                        title="Rename"
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingChatId(conv.id);
                          setEditTitle(conv.title || '');
                        }}
                      >
                        <Edit2 size={13} />
                      </button>
                      <button
                        className="chat-action-btn delete"
                        title="Delete chat"
                        onClick={(e) => handleDelete(conv.id, e)}
                      >
                        <Trash2 size={13} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Main Chat Display */}
      <div className="chat-main-content">
        <div className="chat-page">
          <div className="messages-container">
        {messages.length === 0 && (
          <div className="empty-state text-center" style={{ padding: '48px 20px', color: 'var(--text-muted)' }}>
            <div className="empty-state-icon-wrap" style={{ display: 'inline-flex', padding: '14px', borderRadius: '12px', background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255, 255, 255, 0.1)', marginBottom: '14px' }}>
              <Shield size={28} style={{ color: 'var(--text-primary)' }} />
            </div>
            <h2 style={{ color: 'var(--text-primary)', margin: '0 0 4px 0', fontSize: '1.5rem', fontWeight: 700, letterSpacing: '0.08em' }}>
              CORTEX
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 10px 0' }}>
              Sovereign AI Workspace
            </p>
            <p style={{ fontSize: '0.88rem', maxWidth: '520px', margin: '0 auto 24px auto', lineHeight: 1.5, color: 'var(--text-secondary)' }}>
              Private intelligence for confidential industrial work.
            </p>

            <div className="empty-suggestions-grid">
              <button
                type="button"
                className="suggestion-chip"
                onClick={() => setInput('Analyze this inspection report and generate a formal approval note.')}
              >
                <FileText size={14} />
                <span>Analyze an inspection report</span>
              </button>
              <button
                type="button"
                className="suggestion-chip"
                onClick={() => setInput('What are the vibration velocity thresholds specified in SOP for ISO 10816?')}
              >
                <Search size={14} />
                <span>Search internal SOPs</span>
              </button>
              <button
                type="button"
                className="suggestion-chip"
                onClick={() => setInput('Analyze the uploaded equipment telemetry dataset and detect abnormal readings.')}
              >
                <BarChart3 size={14} />
                <span>Analyze equipment data</span>
              </button>
              <button
                type="button"
                className="suggestion-chip"
                onClick={() => setInput('Generate an engineering approval note with risk assessment.')}
              >
                <CheckCircle2 size={14} />
                <span>Generate an approval note</span>
              </button>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const citationGroups = groupCitationsBySource(msg.citations);

          return (
            <div key={idx} className={`message ${msg.role}`}>
              {msg.role === 'assistant' && (
                <div className="message-header">
                  <Cpu size={14} /> <span>qwen3:4b &middot; Sovereign Local AI</span>
                  {msg.workflowName && (
                    <span className="status-badge success" style={{ marginLeft: '8px', fontSize: '0.7rem' }}>
                      {msg.workflowName}
                    </span>
                  )}
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
                
                {msg.executionPlan && (
                  <div className="task-planner-box">
                    <div className="task-planner-header">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Compass size={15} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>TASK PLANNER &middot; Dynamic Agent Routing</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem' }}>
                        <span className="status-badge info">{msg.executionPlan.intent}</span>
                        <span className="status-badge success">{Math.round((msg.executionPlan.confidence || 0.9) * 100)}% Confidence</span>
                      </div>
                    </div>

                    <div className="task-planner-body">
                      <div className="task-planner-reasoning">
                        {msg.executionPlan.explanation}
                      </div>

                      {msg.executionPlan.planned_agents && msg.executionPlan.planned_agents.length > 0 && (
                        <div className="task-planner-pipeline">
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>EXECUTION PLAN:</span>
                          <div className="task-planner-chips">
                            {msg.executionPlan.planned_agents.map((ag, agIdx) => (
                              <React.Fragment key={agIdx}>
                                <div className="planner-agent-chip">
                                  <GitBranch size={12} />
                                  <span>{ag.toUpperCase()}</span>
                                </div>
                                {agIdx < msg.executionPlan.planned_agents.length - 1 && (
                                  <ArrowRight size={12} style={{ color: 'var(--text-muted)' }} />
                                )}
                              </React.Fragment>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

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

                {msg.coding && (
                  <div className="coding-sandbox-panel">
                    <div className="coding-panel-header">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Terminal size={15} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Local Python Sandbox Execution</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem' }}>
                        {msg.coding.attempts > 1 && (
                          <span className="status-badge warning">Repaired ({msg.coding.attempts} attempts)</span>
                        )}
                        <span className="status-badge success">Exit Code {msg.coding.exit_code}</span>
                        <span style={{ color: 'var(--text-muted)' }}>{msg.coding.execution_time}s</span>
                      </div>
                    </div>

                    {msg.coding.code && (
                      <div className="coding-code-box">
                        <div className="coding-box-title">
                          <Code size={13} />
                          <span>Generated Script</span>
                        </div>
                        <pre className="coding-code-content">{msg.coding.code}</pre>
                      </div>
                    )}

                    {msg.coding.stdout && (
                      <div className="coding-stdout-box">
                        <div className="coding-box-title">
                          <Play size={13} style={{ color: 'var(--success)' }} />
                          <span>Standard Output (stdout)</span>
                        </div>
                        <pre className="coding-stdout-content">{msg.coding.stdout}</pre>
                      </div>
                    )}

                    {msg.coding.stderr && (
                      <div className="coding-stderr-box">
                        <div className="coding-box-title">
                          <AlertCircle size={13} style={{ color: 'var(--danger)' }} />
                          <span>Standard Error (stderr)</span>
                        </div>
                        <pre className="coding-stderr-content">{msg.coding.stderr}</pre>
                      </div>
                    )}
                  </div>
                )}

                {msg.vision && msg.vision.results && msg.vision.results.length > 0 && (
                  <div className="coding-agent-box" style={{ borderColor: 'var(--accent)' }}>
                    <div className="coding-box-header">
                      <div className="coding-title-row">
                        <Eye size={15} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontWeight: 600 }}>VISION AGENT — LOCAL VISUAL ANALYSIS</span>
                      </div>
                      <span className="status-badge info" style={{ fontSize: '0.75rem' }}>
                        Local VLM (Ollama)
                      </span>
                    </div>

                    <div style={{ padding: '10px 14px', fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {msg.vision.results.map((res, vIdx) => (
                        <div key={vIdx} style={{ background: 'var(--bg-secondary)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                            <span style={{ fontWeight: 600, color: 'var(--accent)' }}>
                              Source: {res.file_name} {res.page_number ? `(Page ${res.page_number})` : ''}
                            </span>
                            <span className="status-badge" style={{ fontSize: '0.7rem' }}>
                              Confidence: {res.confidence}
                            </span>
                          </div>

                          {res.description && (
                            <p style={{ margin: '4px 0 8px 0', color: 'var(--text-primary)', fontSize: '0.82rem' }}>
                              {res.description}
                            </p>
                          )}

                          {res.findings && res.findings.length > 0 && (
                            <div style={{ marginTop: '6px' }}>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
                                Detected Elements:
                              </span>
                              <ul style={{ margin: '4px 0', paddingLeft: '18px', color: 'var(--text-secondary)' }}>
                                {res.findings.map((f, fIdx) => (
                                  <li key={fIdx}>
                                    <strong>{f.label || f.type}</strong>
                                    {f.confidence && (
                                      <span style={{ opacity: 0.7, fontSize: '0.75rem', marginLeft: '6px' }}>
                                        ({Math.round(f.confidence * 100)}%)
                                      </span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {res.objects && res.objects.length > 0 && (!res.findings || res.findings.length === 0) && (
                            <div style={{ marginTop: '6px' }}>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
                                Visible Components:
                              </span>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
                                {res.objects.map((obj, oIdx) => (
                                  <span key={oIdx} className="status-badge" style={{ fontSize: '0.75rem', background: 'var(--bg-tertiary)' }}>
                                    {obj}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {res.warnings && res.warnings.length > 0 && (
                            <div style={{ marginTop: '6px', fontSize: '0.75rem', color: 'var(--warning)', display: 'flex', gap: '4px', alignItems: 'center' }}>
                              <AlertCircle size={12} />
                              <span>{res.warnings.join('; ')}</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {msg.dataAnalysis && msg.dataAnalysis.datasets && msg.dataAnalysis.datasets.length > 0 && (
                  <div className="coding-agent-box" style={{ borderColor: 'var(--accent)' }}>
                    <div className="coding-box-header">
                      <div className="coding-title-row">
                        <BarChart3 size={15} style={{ color: 'var(--accent)' }} />
                        <span style={{ fontWeight: 600 }}>DATA ANALYSIS AGENT — DETERMINISTIC LOCAL ANALYTICS</span>
                      </div>
                      <span className="status-badge success" style={{ fontSize: '0.75rem' }}>
                        Local Pandas &amp; Matplotlib
                      </span>
                    </div>

                    <div style={{ padding: '10px 14px', fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {msg.dataAnalysis.key_findings && msg.dataAnalysis.key_findings.length > 0 && (
                        <div style={{ background: 'var(--bg-secondary)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
                            Key Analytical Insights:
                          </span>
                          <ul style={{ margin: '6px 0 2px 0', paddingLeft: '18px', color: 'var(--text-primary)' }}>
                            {msg.dataAnalysis.key_findings.map((finding, fIdx) => (
                              <li key={fIdx} style={{ marginBottom: '3px' }}>{finding}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {msg.dataAnalysis.datasets.map((ds, dIdx) => (
                        <div key={dIdx} style={{ background: 'var(--bg-secondary)', padding: '10px', borderRadius: '6px', border: '1px solid var(--border)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                            <span style={{ fontWeight: 600, color: 'var(--accent)' }}>
                              Dataset: {ds.dataset}
                            </span>
                            <div style={{ display: 'flex', gap: '6px' }}>
                              <span className="status-badge" style={{ fontSize: '0.7rem' }}>
                                {ds.row_count || ds.rows} rows × {ds.columns?.length || 0} cols
                              </span>
                              <span className="status-badge" style={{ fontSize: '0.7rem' }}>
                                Confidence: {ds.confidence || 'high'}
                              </span>
                            </div>
                          </div>

                          {ds.trends && Object.keys(ds.trends).length > 0 && (
                            <div style={{ marginBottom: '8px' }}>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
                                Trend Detection:
                              </span>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                                {Object.entries(ds.trends).map(([col, t], tIdx) => (
                                  <span key={tIdx} className="status-badge" style={{ fontSize: '0.75rem', background: 'var(--bg-tertiary)' }}>
                                    <strong>{col}:</strong> {t.direction} (slope: {t.slope})
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {ds.anomalies && ds.anomalies.length > 0 && (
                            <div style={{ marginBottom: '8px' }}>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--danger)', textTransform: 'uppercase' }}>
                                Statistical Outliers ({ds.anomalies.length}):
                              </span>
                              <ul style={{ margin: '4px 0', paddingLeft: '18px', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                                {ds.anomalies.slice(0, 3).map((ano, aIdx) => (
                                  <li key={aIdx}>
                                    Column <strong>{ano.column}</strong> at row {ano.row_index}: value {ano.value} (threshold {ano.threshold})
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {ds.charts && ds.charts.length > 0 && (
                            <div style={{ marginTop: '8px' }}>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
                                Local Generated Charts:
                              </span>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                                {ds.charts.map((ch, cIdx) => (
                                  <span key={cIdx} className="status-badge" style={{ fontSize: '0.75rem', background: 'var(--bg-tertiary)', color: 'var(--accent)' }}>
                                    ✓ {ch.filename || `Chart ${cIdx + 1}`} ({ch.kind})
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {citationGroups.length > 0 && (
                  <div className="citations-section">
                    <div className="citations-header">
                      <FileText size={15} style={{ color: 'var(--accent)' }} />
                      <span>Knowledge Base Citations &amp; Evidence</span>
                    </div>

                    <div className="citation-groups">
                      {citationGroups.map((group, gi) => (
                        <div key={gi} className="citation-group">
                          <div className="citation-group-header">
                            <div className="citation-source-title">
                              <File size={14} style={{ color: group.category === 'sop' ? 'var(--accent)' : 'var(--warning)' }} />
                              <span>{group.filename}</span>
                            </div>
                            <span className={`citation-badge ${group.category}`}>
                              {group.categoryLabel}
                            </span>
                          </div>

                          <div className="citation-items">
                            {group.items.map((item, ci) => (
                              <div key={ci} className={`citation-item ${group.category === 'report' ? 'report-item' : ''}`}>
                                <div className="citation-item-meta">
                                  <span>Page {item.page || 1}</span>
                                  <span style={{ opacity: 0.7 }}>{item.citation}</span>
                                </div>
                                {item.text && (
                                  <div className="citation-item-text">
                                    {item.text.length > 280 ? `${item.text.slice(0, 280)}...` : item.text}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {msg.artifacts && msg.artifacts.length > 0 && (
                  <div className="artifacts-section">
                    <div className="artifacts-header">
                      <Download size={15} style={{ color: 'var(--success)' }} />
                      <span>Generated Artifacts &amp; Approval Deliverables</span>
                    </div>

                    <div className="artifacts-grid">
                      {msg.artifacts.map((art, i) => {
                        const filename = art.filename || (art.path ? art.path.split(/[\\/]/).pop() : `Deliverable_${i + 1}`);
                        const meta = getArtifactMeta(filename);
                        const downloadHref = art.download_url
                          ? `http://localhost:8000${art.download_url}`
                          : `http://localhost:8000/api/artifacts/${art.id}/download`;

                        return (
                          <a
                            key={i}
                            href={downloadHref}
                            target="_blank"
                            rel="noreferrer"
                            className={`artifact-card ${meta.isProminent ? 'prominent' : ''}`}
                            title={`Download ${filename}`}
                          >
                            <div className="artifact-card-left">
                              <div className={`artifact-icon-wrap ${meta.type}`}>
                                {meta.ext === 'XLSX' ? (
                                  <FileSpreadsheet size={18} />
                                ) : meta.ext === 'PPTX' ? (
                                  <Presentation size={18} />
                                ) : (
                                  <FileText size={18} />
                                )}
                              </div>
                              <div className="artifact-info">
                                <span className="artifact-filename">{filename}</span>
                                <div className="artifact-badge-row">
                                  <span className="artifact-type-tag">{meta.ext}</span>
                                  {meta.isApproval && (
                                    <span className="artifact-approval-tag">Approval Note</span>
                                  )}
                                </div>
                              </div>
                            </div>

                            <div className="artifact-download-action">
                              <Download size={13} />
                              <span>Download</span>
                            </div>
                          </a>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

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
        </div>
      </div>
  );
}

export default ChatPage;
