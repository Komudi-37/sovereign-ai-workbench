import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import CortexFlowBackground from './components/CortexFlowBackground';
import { Hero } from './components/ui/tailwind-css-background-snippet';
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
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden' }}>
        <Hero />
      </div>
      <CortexFlowBackground />
      <Header />
      <div className="app-body">
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
