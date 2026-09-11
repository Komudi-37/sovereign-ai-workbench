import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import ChatPage from './pages/ChatPage';
import DocumentsPage from './pages/DocumentsPage';
import KnowledgePage from './pages/KnowledgePage';
import WorkflowsPage from './pages/WorkflowsPage';
import ArtifactsPage from './pages/ArtifactsPage';
import AuditPage from './pages/AuditPage';
import SecurityPage from './pages/SecurityPage';
import './App.css';

function App() {
  return (
    <div className="app">
      <Header />
      <div className="app-body">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/workflows" element={<WorkflowsPage />} />
            <Route path="/artifacts" element={<ArtifactsPage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route path="/security" element={<SecurityPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default App;
