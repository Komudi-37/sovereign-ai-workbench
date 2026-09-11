import React from 'react';
import { NavLink } from 'react-router-dom';
import { MessageSquare, FileText, BookOpen, GitBranch, Download, ClipboardList, Shield } from 'lucide-react';

function Sidebar() {
  const links = [
    { to: '/', label: 'Chat', icon: <MessageSquare size={18} /> },
    { to: '/documents', label: 'Documents', icon: <FileText size={18} /> },
    { to: '/knowledge', label: 'Knowledge Base', icon: <BookOpen size={18} /> },
    { to: '/workflows', label: 'Workflows', icon: <GitBranch size={18} /> },
    { to: '/artifacts', label: 'Artifacts', icon: <Download size={18} /> },
    { to: '/audit', label: 'Audit Log', icon: <ClipboardList size={18} /> },
    { to: '/security', label: 'Security', icon: <Shield size={18} /> },
  ];

  return (
    <div className="sidebar">
      <nav className="nav-menu">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
          >
            {link.icon}
            <span>{link.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        v1.0 &middot; All Local
      </div>
    </div>
  );
}

export default Sidebar;
