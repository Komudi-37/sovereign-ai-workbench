import React, { useState, useEffect } from 'react';
import { GitBranch, ChevronDown, ChevronUp } from 'lucide-react';
import { listWorkflows } from '../api';

function WorkflowsPage() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);

  useEffect(() => {
    const fetchWorkflows = async () => {
      try {
        const data = await listWorkflows();
        setWorkflows(data.workflows || data);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchWorkflows();
  }, []);

  const toggleRow = (id) => {
    setExpandedRow(expandedRow === id ? null : id);
  };

  const getStatusClass = (status) => {
    switch (status?.toLowerCase()) {
      case 'completed': return 'success';
      case 'failed': return 'danger';
      case 'partial': return 'warning';
      default: return 'warning'; // running or other
    }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>Workflows</h2>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Request</th>
              <th>Type</th>
              <th>Status</th>
              <th>Agents</th>
              <th>Started</th>
              <th>Completed</th>
              <th>Artifacts</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {workflows.map((wf) => (
              <React.Fragment key={wf.id}>
                <tr className="cursor-pointer" onClick={() => toggleRow(wf.id)}>
                  <td>{wf.id.substring(0, 8)}...</td>
                  <td>{wf.request || wf.message || 'N/A'}</td>
                  <td>{wf.workflow_type || wf.workflow || 'auto'}</td>
                  <td>
                    <span className={`status-badge ${getStatusClass(wf.status)}`}>
                      {wf.status || 'running'}
                    </span>
                  </td>
                  <td>{wf.agents?.length || 0}</td>
                  <td>{new Date(wf.started_at || wf.created_at).toLocaleString()}</td>
                  <td>{wf.completed_at ? new Date(wf.completed_at).toLocaleString() : '-'}</td>
                  <td>{wf.artifacts?.length || 0}</td>
                  <td>
                    {expandedRow === wf.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </td>
                </tr>
                {expandedRow === wf.id && (
                  <tr className="expanded-row">
                    <td colSpan="9">
                      <div className="timeline">
                        <h4>Agent Execution Timeline</h4>
                        {(wf.timeline || []).map((item, i) => (
                          <div key={i} className="timeline-item">
                            {item.status === 'completed' ? '✓' : '●'} {item.label}
                          </div>
                        ))}
                        {(!wf.timeline || wf.timeline.length === 0) && <p className="text-muted">No timeline data available.</p>}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
            {workflows.length === 0 && !loading && (
              <tr>
                <td colSpan="9" className="text-center">No workflows found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default WorkflowsPage;
