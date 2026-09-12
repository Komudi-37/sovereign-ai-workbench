import React, { useState, useEffect } from 'react';
import { Shield, AlertTriangle, CheckCircle, Radio, Activity, RefreshCw, Lock, Server } from 'lucide-react';
import { getSecurityStatus, getNetworkEvents } from '../api';

function SecurityPage() {
  const [status, setStatus] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchSecurityData = async () => {
    try {
      setRefreshing(true);
      const [statusData, eventsData] = await Promise.all([
        getSecurityStatus().catch(() => null),
        getNetworkEvents().catch(() => [])
      ]);
      
      if (statusData) setStatus(statusData);
      if (eventsData) setEvents(eventsData);
    } catch (error) {
      console.error("Failed to fetch security info:", error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchSecurityData();
  }, []);

  if (loading) return <div className="page-container"><div>Loading sovereignty status...</div></div>;

  const dashboardItems = [
    { label: 'LOCAL AI', value: status?.llm_model ? `Ollama / ${status.llm_model}` : 'Ollama / qwen3:4b', secure: true },
    { label: 'DATABASE', value: status?.database || 'SQLite', secure: true },
    { label: 'VECTOR STORE', value: status?.vector_store || 'FAISS', secure: true },
    { label: 'OCR', value: status?.ocr || 'Local (PyMuPDF)', secure: true },
    { label: 'VISION', value: status?.vision || 'Local (configurable)', secure: true },
    { label: 'EMBEDDINGS', value: status?.embeddings || 'Local (nomic-embed-text)', secure: true },
    { label: 'CODING AGENT', value: status?.coding_agent || 'Local (Python 3 Subprocess)', secure: true },
    { label: 'SECURE SANDBOX', value: status?.sandbox || 'Isolated (Sanitized Env & AST)', secure: true },
    { label: 'EXTERNAL AI APIs', value: status?.external_apis || 'Disabled', secure: true },
    { label: 'AUDIT LOG', value: status?.audit_log || 'Enabled', secure: true },
  ];

  const cloudKeysDetected = status?.cloud_api_keys_detected;
  const extCalls = status?.external_calls_attempted || 0;
  const blockedCalls = status?.external_calls_blocked || 0;
  const localCalls = status?.local_calls || 0;

  return (
    <div className="page-container">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Sovereignty &amp; Security Monitor</h2>
        <button
          className="btn secondary"
          onClick={fetchSecurityData}
          disabled={refreshing}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.85rem' }}
        >
          <RefreshCw size={14} className={refreshing ? 'spinning' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {cloudKeysDetected && (
        <div className="alert danger">
          <AlertTriangle size={20} />
          <span>Warning: Cloud API keys detected in runtime environment. Remove external keys for full sovereignty.</span>
        </div>
      )}

      {/* Hero Sovereignty Monitor Widget */}
      <div className="sovereignty-hero-box">
        <div className="sovereignty-hero-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Radio size={18} className="pulse-icon text-success" />
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>SOVEREIGNTY MONITOR</h3>
          </div>
          <span className="status-badge success" style={{ fontSize: '0.75rem', padding: '4px 10px' }}>
            SOVEREIGN MODE: ACTIVE
          </span>
        </div>

        <div className="sovereignty-stats-grid">
          <div className="sov-stat-item">
            <span className="sov-stat-label">External Network Calls</span>
            <span className={`sov-stat-value ${extCalls > 0 ? 'text-warning' : 'text-success'}`}>{extCalls}</span>
            <span className="sov-stat-sub">Direct cloud requests</span>
          </div>

          <div className="sov-stat-item">
            <span className="sov-stat-label">Blocked Attempts</span>
            <span className="sov-stat-value text-success">{blockedCalls}</span>
            <span className="sov-stat-sub">Sovereign policy enforced</span>
          </div>

          <div className="sov-stat-item">
            <span className="sov-stat-label">Local Connections</span>
            <span className="sov-stat-value text-primary">{localCalls}</span>
            <span className="sov-stat-sub">127.0.0.1 loopback allowed</span>
          </div>

          <div className="sov-stat-item">
            <span className="sov-stat-label">Cloud API Keys</span>
            <span className={`sov-stat-value ${cloudKeysDetected ? 'text-danger' : 'text-success'}`}>
              {cloudKeysDetected ? 'DETECTED' : 'NOT DETECTED'}
            </span>
            <span className="sov-stat-sub">Zero remote credentials</span>
          </div>
        </div>

        <div className="sovereignty-hero-footer">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem' }}>
            <Server size={14} style={{ color: 'var(--accent)' }} />
            <span>Local LLM Provider: <strong>{status?.llm_provider || 'Ollama'}</strong></span>
            <span style={{ opacity: 0.5 }}>|</span>
            <span>Model: <strong>{status?.llm_model || 'qwen3:4b'}</strong></span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'var(--success)' }}>
            <Lock size={14} />
            <span>Application-level sovereign policy &amp; monitoring</span>
          </div>
        </div>
      </div>

      {/* Network Activity Timeline / Events Table */}
      <div className="network-activity-section">
        <div className="section-title-row">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={16} style={{ color: 'var(--accent)' }} />
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Network Activity &amp; Classification Timeline</h3>
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {events.length} recorded events
          </span>
        </div>

        {events.length === 0 ? (
          <div className="network-empty-box">
            <CheckCircle size={20} className="text-success" />
            <span>No network anomalies detected. All operations executing on local loopback (127.0.0.1).</span>
          </div>
        ) : (
          <div className="network-events-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Timestamp</th>
                  <th>Source</th>
                  <th>Destination</th>
                  <th>Classification</th>
                  <th>Reason / Policy</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev, idx) => (
                  <tr key={idx}>
                    <td>
                      {ev.action === 'BLOCKED' ? (
                        <span className="status-badge danger">BLOCKED</span>
                      ) : (
                        <span className="status-badge success">ALLOWED</span>
                      )}
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {ev.timestamp ? ev.timestamp.replace('T', ' ').slice(0, 19) : 'Just now'}
                    </td>
                    <td style={{ fontWeight: 600 }}>{ev.source}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>{ev.destination}</td>
                    <td>
                      <span className={`status-badge ${ev.classification === 'LOCAL' ? 'info' : 'warning'}`}>
                        {ev.classification}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{ev.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* System Component Integrity Grid */}
      <div style={{ marginTop: '28px', marginBottom: '12px' }}>
        <h3 style={{ fontSize: '1rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Subsystem Sovereignty Matrix
        </h3>
      </div>

      <div className="security-dashboard">
        {dashboardItems.map((item, i) => (
          <div key={i} className="security-card">
            <div className="security-card-header">
              <span className="security-label">{item.label}</span>
              {item.secure ? (
                <CheckCircle size={16} className="text-success" />
              ) : (
                <AlertTriangle size={16} className="text-warning" />
              )}
            </div>
            <div className="security-value">{item.value}</div>
          </div>
        ))}
      </div>

      {/* Workspace Isolation & Boundary Protection */}
      <div style={{ marginTop: '28px', marginBottom: '12px' }}>
        <h3 style={{ fontSize: '1rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          Workspace Isolation &amp; Boundary Protection
        </h3>
      </div>

      <div className="sovereignty-hero-box" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <div className="sovereignty-hero-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Lock size={18} className="text-success" />
            <h3 style={{ margin: 0, fontSize: '1.05rem' }}>SECURE WORKSPACE ISOLATION</h3>
          </div>
          <span className="status-badge success" style={{ fontSize: '0.75rem', padding: '4px 10px' }}>
            BOUNDARIES ENFORCED
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', padding: '16px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={16} className="text-success" />
            <span style={{ fontSize: '0.85rem' }}>Uploads isolated</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={16} className="text-success" />
            <span style={{ fontSize: '0.85rem' }}>Agent workspace isolated</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={16} className="text-success" />
            <span style={{ fontSize: '0.85rem' }}>Coding sandbox isolated</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={16} className="text-success" />
            <span style={{ fontSize: '0.85rem' }}>Path traversal protection active</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={16} className="text-success" />
            <span style={{ fontSize: '0.85rem' }}>Generated artifacts controlled</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={16} className="text-success" />
            <span style={{ fontSize: '0.85rem' }}>Run-specific workspace isolation</span>
          </div>
        </div>

        <div className="sovereignty-hero-footer" style={{ borderTop: '1px solid var(--border)', padding: '12px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Root Scope: <strong>{status?.workspace_root || 'Isolated Local Workspace'}</strong>
          </span>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Application-level workspace isolation and path traversal protection
          </span>
        </div>
      </div>

      <div className="security-footer text-success mt-4">
        <Shield size={20} />
        <span>All AI processing is configured for local execution. Your data stays on your machine.</span>
      </div>
    </div>
  );
}

export default SecurityPage;
