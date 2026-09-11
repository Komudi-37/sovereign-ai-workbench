import React, { useState, useEffect, useRef } from 'react';
import { Upload, File, RefreshCw, Play } from 'lucide-react';
import { listFiles, uploadFile, indexDocument } from '../api';

function DocumentsPage() {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const data = await listFiles();
      setFiles(data.files || data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  const handleFileUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      await uploadFile(file);
      await fetchFiles();
    } catch (error) {
      console.error(error);
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleIndex = async (id) => {
    try {
      await indexDocument(id);
      await fetchFiles(); // refresh to show updated status
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>Documents</h2>
        <button className="btn" onClick={fetchFiles} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div 
        className="upload-dropzone" 
        onDragOver={(e) => e.preventDefault()} 
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload size={32} />
        <p>{uploading ? 'Uploading...' : 'Click or drag file to this area to upload'}</p>
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={(e) => handleFileUpload(e.target.files[0])} 
          style={{ display: 'none' }} 
        />
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Filename</th>
              <th>Type</th>
              <th>Size</th>
              <th>Date</th>
              <th>Indexed</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {files.map((file) => (
              <tr key={file.id}>
                <td>
                  <div className="flex-row"><File size={16}/> {file.filename}</div>
                </td>
                <td>{file.type || 'Unknown'}</td>
                <td>{(file.size / 1024).toFixed(2)} KB</td>
                <td>{new Date(file.created_at).toLocaleString()}</td>
                <td>
                  <span className={`status-badge ${file.is_indexed ? 'success' : 'warning'}`}>
                    {file.is_indexed ? 'Indexed' : 'Not Indexed'}
                  </span>
                </td>
                <td>
                  <button 
                    className="btn small primary" 
                    onClick={() => handleIndex(file.id)}
                    disabled={file.is_indexed}
                  >
                    <Play size={14}/> Index
                  </button>
                </td>
              </tr>
            ))}
            {files.length === 0 && !loading && (
              <tr>
                <td colSpan="6" className="text-center">No documents found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default DocumentsPage;
