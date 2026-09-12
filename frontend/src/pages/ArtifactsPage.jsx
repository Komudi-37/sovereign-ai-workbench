import React, { useState, useEffect } from 'react';
import { Download, File as FileIcon, Image, Code, FileText, FileSpreadsheet, Presentation } from 'lucide-react';
import { listArtifacts, downloadArtifact } from '../api';

function ArtifactsPage() {
  const [artifacts, setArtifacts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchArtifacts = async () => {
      try {
        const data = await listArtifacts();
        setArtifacts(data.artifacts || data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchArtifacts();
  }, []);

  const getIconForType = (filename) => {
    if (!filename) return <FileIcon size={24} />;
    const ext = filename.split('.').pop().toLowerCase();
    if (['png', 'jpg', 'jpeg', 'gif'].includes(ext)) return <Image size={24} />;
    if (['py', 'js', 'html', 'css', 'json'].includes(ext)) return <Code size={24} />;
    if (['xlsx', 'xls', 'csv'].includes(ext)) return <FileSpreadsheet size={24} color="#107c41" />;
    if (['pptx', 'ppt'].includes(ext)) return <Presentation size={24} color="#d24726" />;
    if (['txt', 'md', 'pdf', 'docx', 'doc'].includes(ext)) return <FileText size={24} />;
    return <FileIcon size={24} />;
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>Artifacts</h2>
      </div>

      <div className="artifacts-grid">
        {artifacts.map((art) => (
          <div key={art.id} className="artifact-card">
            <div className="artifact-icon">
              {getIconForType(art.filename)}
            </div>
            <div className="artifact-info">
              <h4 className="artifact-title">{art.filename}</h4>
              <p className="artifact-meta">Agent: {art.agent_name || 'System'}</p>
              <p className="artifact-meta">{new Date(art.created_at).toLocaleString()}</p>
              <p className="artifact-meta">{(art.size / 1024).toFixed(2)} KB</p>
            </div>
            <button className="btn primary small artifact-dl-btn" onClick={() => downloadArtifact(art.id)}>
              <Download size={14} /> Download
            </button>
          </div>
        ))}
        {artifacts.length === 0 && !loading && (
          <p className="text-muted">No artifacts found.</p>
        )}
      </div>
    </div>
  );
}

export default ArtifactsPage;
