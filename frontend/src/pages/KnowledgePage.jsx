import React, { useState } from 'react';
import { Search, BookOpen } from 'lucide-react';
import { searchKnowledge } from '../api';

function KnowledgePage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    
    setLoading(true);
    try {
      const data = await searchKnowledge(query);
      setResults(data.results || data);
      setSearched(true);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h2>Knowledge Base</h2>
      </div>

      <div className="stats-cards">
        <div className="stat-card">
          <BookOpen size={24} className="text-accent" />
          <div className="stat-info">
            <span className="stat-value">--</span>
            <span className="stat-label">Total Documents Indexed</span>
          </div>
        </div>
        <div className="stat-card">
          <BookOpen size={24} className="text-accent" />
          <div className="stat-info">
            <span className="stat-value">--</span>
            <span className="stat-label">Total Chunks</span>
          </div>
        </div>
      </div>

      <form className="search-bar" onSubmit={handleSearch}>
        <Search size={20} className="search-icon" />
        <input 
          type="text" 
          value={query} 
          onChange={(e) => setQuery(e.target.value)} 
          placeholder="Search knowledge base..." 
        />
        <button type="submit" className="btn primary" disabled={loading}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>

      <div className="search-results">
        {searched && results.length === 0 && <p className="text-muted">No results found.</p>}
        {results.map((res, idx) => (
          <div key={idx} className="result-card">
            <p className="result-text">{res.text || res.content}</p>
            <div className="result-meta">
              <span className="citation">[Source: {res.filename || res.source}, page {res.page || 1}]</span>
              <span className="score">Relevance Score: {(res.score || res.relevance || 0).toFixed(2)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default KnowledgePage;
