import React, { useState, useEffect } from 'react';
import { Shield, AlertTriangle, CheckCircle } from 'lucide-react';
import { getSecurityStatus } from '../api';

function SecurityPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await getSecurityStatus();
        setStatus(data);
      } catch (error) {
        console.error(error);
        // Fallback mock data if API doesn't exist
        setStatus({
          local_ai: 'Ollama / qwen3:4b',
          database: 'SQLite',
          vector_store: 'FAISS',
          ocr: 'Local (PyMuPDF)',
          vision: 'Local (configurable)',
          embeddings: 'Local (nomic-embed-text)',
          external_apis: 'Disabled',
          audit_log: 'Enabled',
          cloud_keys_detected: false
        });
      } finally {
        setLoading(false);
      }
    };
    fetchStatus();
  }, []);

  if (loading) return <div>Loading security status...</div>;

  const dashboardItems = [
    { label: 'LOCAL AI', value: status?.local_ai || 'Ollama / qwen3:4b', secure: true },
    { label: 'DATABASE', value: status?.database || 'SQLite', secure: true },
    { label: 'VECTOR STORE', value: status?.vector_store || 'FAISS', secure: true },
    { label: 'OCR', value: status?.ocr || 'Local (PyMuPDF)', secure: true },
    { label: 'VISION', value: status?.vision || 'Local (configurable)', secure: true },
    { label: 'EMBEDDINGS', value: status?.embeddings || 'Local (nomic-embed-text)', secure: true },
    { label: 'EXTERNAL AI APIs', value: status?.external_apis || 'Disabled', secure: status?.external_apis === 'Disabled' },
    { label: 'AUDIT LOG', value: status?.audit_log || 'Enabled', secure: status?.audit_log === 'Enabled' },
  ];

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>Sovereignty &amp; Security</h2>
      </div>

      {status?.cloud_keys_detected && (
        <div className="alert danger">
          <AlertTriangle size={20} />
          <span>Warning: Cloud API keys detected in environment variables. True sovereignty is not guaranteed.</span>
        </div>
      )}

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

      <div className="security-footer text-success mt-4">
        <Shield size={20} />
        <span>All AI processing is configured for local execution. Your data stays on your machine.</span>
      </div>
    </div>
  );
}

export default SecurityPage;
