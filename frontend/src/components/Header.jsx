import React, { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Shield, Cpu, Lock, MessageSquare, FileText, BookOpen,
  GitBranch, Download, ClipboardList, Menu, X
} from 'lucide-react';
import { checkHealth } from '../api';

function Header() {
  const [isHealthy, setIsHealthy] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    checkHealth()
      .then((data) => setIsHealthy(data.status === 'ok'))
      .catch(() => setIsHealthy(false));
  }, []);

  const navLinks = [
    { to: '/', label: 'Chat', icon: <MessageSquare size={16} /> },
    { to: '/documents', label: 'Documents', icon: <FileText size={16} /> },
    { to: '/knowledge', label: 'Knowledge Base', icon: <BookOpen size={16} /> },
    { to: '/workflows', label: 'Workflows', icon: <GitBranch size={16} /> },
    { to: '/artifacts', label: 'Artifacts', icon: <Download size={16} /> },
    { to: '/audit', label: 'Audit Log', icon: <ClipboardList size={16} /> },
    { to: '/security', label: 'Security', icon: <Shield size={16} /> },
  ];

  return (
    <header className="top-header">
      <div className="header-brand">
        <div className="brand-logo-wrap">
          <Shield className="header-icon" size={18} />
        </div>
        <div className="brand-text-wrap">
          <span className="header-title">CORTEX</span>
          <span className="header-subtitle">Sovereign AI Workspace</span>
        </div>
      </div>

      <nav className={`top-nav ${mobileMenuOpen ? 'mobile-open' : ''}`}>
        {navLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => (isActive ? 'top-nav-link active' : 'top-nav-link')}
            onClick={() => setMobileMenuOpen(false)}
          >
            {link.icon}
            <span>{link.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="header-right">
        <div className="status-badge success">
          <Lock size={13} /> <span>LOCAL</span>
        </div>
        <div className="status-badge success">
          <Shield size={13} /> <span>SECURE</span>
        </div>
        <div className={`status-badge ${isHealthy ? 'success' : 'danger'}`}>
          <Cpu size={13} /> <span>OLLAMA</span>
        </div>

        <button
          className="mobile-nav-toggle"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
    </header>
  );
}

export default Header;
