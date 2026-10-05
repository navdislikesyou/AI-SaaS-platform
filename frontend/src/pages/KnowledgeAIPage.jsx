import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import Navigation from '../components/Navigation';

const SAMPLE_QUERIES = [
  'What is our employee leave policy?',
  'How many vacation days do employees get?',
  'What is the remote work policy?',
  'How do I submit a performance review?',
];

const KNOWLEDGE_RESULTS = {
  leave: {
    query: 'What is our employee leave policy?',
    answer: 'Employees are entitled to 20 days of annual paid leave per calendar year, accrued at 1.67 days per month. Leave must be requested via the HR portal with a minimum of 3 business days notice for planned leave. Sick leave is separate at 10 days annually. Maternity/paternity leave follows statutory requirements with an additional 4 weeks company-paid extension.',
    sources: [
      { name: 'Employee Handbook.pdf', section: 'Section 5.2 — Leave Policy', pages: '24–27', access: true },
      { name: 'Leave Policy.pdf', section: 'Annual Leave Entitlement', pages: '1–4', access: true },
      { name: 'HR Guidelines.pdf', section: 'Leave Application Process', pages: '8–9', access: true },
    ],
    confidence: 97,
  },
  default: {
    query: 'What is our remote work policy?',
    answer: 'The organization follows a hybrid-first approach. Employees may work remotely up to 3 days per week, with a minimum of 2 in-office days required for team coordination. Full remote arrangements require written approval from department heads and are subject to quarterly review.',
    sources: [
      { name: 'Remote Work Policy.pdf', section: 'Hybrid Work Framework', pages: '1–3', access: true },
      { name: 'Employee Handbook.pdf', section: 'Section 3.1 — Work Arrangements', pages: '14–16', access: true },
    ],
    confidence: 91,
  },
};

export default function KnowledgeAIPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [flowStep, setFlowStep] = useState(0);

  const handleSearch = async (q) => {
    const searchQuery = q || query;
    if (!searchQuery.trim()) return;
    setQuery(searchQuery);
    setSearching(true);
    setResult(null);
    setFlowStep(0);

    // Simulate flow
    for (let i = 1; i <= 4; i++) {
      await new Promise(r => setTimeout(r, 400));
      setFlowStep(i);
    }
    await new Promise(r => setTimeout(r, 300));
    const key = searchQuery.toLowerCase().includes('leave') ? 'leave' : 'default';
    setResult(KNOWLEDGE_RESULTS[key]);
    setSearching(false);
  };

  const FLOW_STEPS = ['Query', 'Retrieval', 'Documents', 'Context', 'Answer'];

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main">

        <div className="agent-hero knowledge-hero">
          <div className="agent-hero-inner">
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9 }}>
              <div className="agent-hero-breadcrumb">
                <button onClick={() => navigate('/agents')} className="breadcrumb-back">AI Agents</button>
                <span>→</span><span>Knowledge AI</span>
              </div>
              <div className="agent-num-label">03</div>
              <h1 className="agent-hero-heading knowledge">KNOWLEDGE AI</h1>
              <p className="agent-hero-tagline">Ask your<br />organization.</p>
            </motion.div>
            <motion.div className="agent-hero-stats" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
              <div className="agent-stat"><span className="agent-stat-value">1,240</span><span className="agent-stat-label">Documents Indexed</span></div>
              <div className="agent-stat"><span className="agent-stat-value">99%</span><span className="agent-stat-label">Retrieval Accuracy</span></div>
              <div className="agent-stat"><span className="agent-stat-value">1.2s</span><span className="agent-stat-label">Avg. Response Time</span></div>
            </motion.div>
          </div>
        </div>

        <div className="agent-workspace knowledge-workspace">

          {/* Search + flow */}
          <motion.div className="knowledge-search-col" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <div className="knowledge-search-wrap">
              <div className="knowledge-input-wrap">
                <input
                  type="text"
                  className="knowledge-input"
                  placeholder="Ask anything about your organization..."
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                />
                <button className="knowledge-search-btn" onClick={() => handleSearch()}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                  </svg>
                </button>
              </div>

              <div className="knowledge-samples">
                {SAMPLE_QUERIES.map((q, i) => (
                  <button key={i} className="knowledge-sample" onClick={() => handleSearch(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* RAG Flow visualization */}
            <div className="rag-flow">
              <div className="workspace-panel-header">
                <span className="workspace-panel-label">Retrieval Flow</span>
              </div>
              <div className="rag-flow-steps">
                {FLOW_STEPS.map((step, i) => (
                  <div key={step} className="rag-flow-item">
                    <div className={`rag-step-node ${flowStep >= i + 1 ? 'active' : ''} ${flowStep === i + 1 && searching ? 'current' : ''}`}>
                      <span>{i + 1}</span>
                    </div>
                    <span className={`rag-step-label ${flowStep >= i + 1 ? 'active' : ''}`}>{step}</span>
                    {i < FLOW_STEPS.length - 1 && (
                      <div className={`rag-step-connector ${flowStep > i + 1 ? 'active' : ''}`} />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          {/* Results */}
          <motion.div className="workspace-panel wide-panel" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <AnimatePresence mode="wait">
              {searching && (
                <motion.div key="searching" className="knowledge-searching" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  <div className="searching-spinner" />
                  <p>Searching organization knowledge...</p>
                </motion.div>
              )}
              {result && !searching && (
                <motion.div key="result" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
                  <div className="workspace-panel-header">
                    <span className="workspace-panel-label">AI Answer</span>
                    <div className="access-verified">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                      </svg>
                      ACCESS VERIFIED
                    </div>
                  </div>

                  <div className="knowledge-query-display">
                    <span className="knowledge-query-label">Query</span>
                    <p className="knowledge-query-text">"{result.query}"</p>
                  </div>

                  <div className="knowledge-answer">
                    <p className="knowledge-answer-text">{result.answer}</p>
                  </div>

                  <div className="knowledge-confidence">
                    <span className="confidence-label">Confidence</span>
                    <div className="confidence-bar-wrap">
                      <div className="confidence-bar">
                        <motion.div
                          className="confidence-fill"
                          initial={{ width: 0 }}
                          animate={{ width: `${result.confidence}%` }}
                          transition={{ duration: 0.8, delay: 0.3 }}
                        />
                      </div>
                      <span className="confidence-value">{result.confidence}%</span>
                    </div>
                  </div>

                  <div className="knowledge-sources">
                    <div className="workspace-field-label">Relevant Sources</div>
                    {result.sources.map((s, i) => (
                      <motion.div
                        key={i}
                        className="source-item"
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.1 }}
                      >
                        <div className="source-icon">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                          </svg>
                        </div>
                        <div className="source-info">
                          <span className="source-name">{s.name}</span>
                          <span className="source-section">{s.section} · Pages {s.pages}</span>
                        </div>
                        <div className="source-access">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                          </svg>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              )}
              {!result && !searching && (
                <motion.div key="empty" className="knowledge-empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <div className="knowledge-empty-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                      <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                    </svg>
                  </div>
                  <p>Ask anything about your organization's documents, policies, and knowledge base.</p>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
