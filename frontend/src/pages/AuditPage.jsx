import React, { useState, useEffect } from 'react';
import { ClipboardList, RefreshCw } from 'lucide-react';
import { listAuditLogs } from '../api';

function AuditPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const data = await listAuditLogs();
      setLogs(data.logs || data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const getActionColor = (action) => {
    const a = action?.toLowerCase() || '';
    if (a.includes('create') || a.includes('upload') || a.includes('start')) return 'text-success';
    if (a.includes('delete') || a.includes('fail')) return 'text-danger';
    if (a.includes('update') || a.includes('modify')) return 'text-warning';
    return 'text-accent';
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>Audit Log</h2>
        <button className="btn" onClick={fetchLogs} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Action</th>
              <th>Agent/User</th>
              <th>Resource</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{new Date(log.timestamp || log.created_at).toLocaleString()}</td>
                <td className={getActionColor(log.action)}>
                  <strong>{log.action}</strong>
                </td>
                <td>{log.actor || log.agent || 'User'}</td>
                <td>{log.resource || '-'}</td>
                <td>{log.details || '-'}</td>
              </tr>
            ))}
            {logs.length === 0 && !loading && (
              <tr>
                <td colSpan="5" className="text-center">No audit logs found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default AuditPage;
