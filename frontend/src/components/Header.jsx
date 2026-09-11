import React, { useEffect, useState } from 'react';
import { Shield, Cpu, Lock } from 'lucide-react';
import { checkHealth } from '../api';

function Header() {
  const [isHealthy, setIsHealthy] = useState(true);

  useEffect(() => {
    checkHealth()
      .then((data) => setIsHealthy(data.status === 'ok'))
      .catch(() => setIsHealthy(false));
  }, []);

  return (
    <header className="header">
      <div className="header-left">
        <Shield className="header-icon" />
        <span className="header-title">Sovereign AI Workbench</span>
      </div>
      <div className="header-right">
        <div className="status-badge success">
          <Lock size={14} /> LOCAL
        </div>
        <div className="status-badge success">
          <Shield size={14} /> SECURE
        </div>
        <div className={`status-badge ${isHealthy ? 'success' : 'danger'}`}>
          <Cpu size={14} /> Ollama
        </div>
      </div>
    </header>
  );
}

export default Header;
