import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import Navigation from '../components/Navigation';

const PAPERS = [
  {
    id: 1,
    title: 'Attention Is All You Need',
    authors: 'Vaswani et al.',
    year: '2017',
    topic: 'Transformer Architecture',
    relevance: 98,
    quality: 'Landmark',
    summary: 'Introduces the Transformer architecture, replacing recurrence and convolutions with attention mechanisms entirely. Foundational to modern LLM development.',
    keyFindings: [
      'Attention mechanisms can replace RNNs entirely for sequence modeling',
      'Multi-head attention enables learning relationships at different positions',
      'Positional encoding preserves sequence order without recurrence',
      'Model achieves BLEU score of 28.4 on WMT 2014 English-to-German translation',
    ],
    references: 41,
  },
  {
    id: 2,
    title: 'BERT: Pre-training Deep Bidirectional Transformers',
    authors: 'Devlin et al.',
    year: '2019',
    topic: 'Language Representation',
    relevance: 91,
    quality: 'High',
    summary: 'BERT introduces masked language modeling and next sentence prediction for bidirectional pre-training, achieving state-of-the-art on 11 NLP tasks.',
    keyFindings: [
      'Bidirectional context representation significantly outperforms unidirectional models',
      'Masked Language Model pretraining enables deep bidirectionality',
      'Fine-tuning a single model across diverse tasks reduces task-specific architecture',
    ],
    references: 63,
  },
];

export default function ResearchAIPage() {
  const navigate = useNavigate();
  const [activePaper, setActivePaper] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);

  const handleUpload = () => {
    setUploading(true);
    setTimeout(() => { setUploading(false); setUploaded(true); }, 2000);
  };

  const paper = PAPERS[activePaper];

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main">

        <div className="agent-hero research-hero">
          <div className="agent-hero-inner">
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9 }}>
              <div className="agent-hero-breadcrumb">
                <button onClick={() => navigate('/agents')} className="breadcrumb-back">AI Agents</button>
                <span>→</span><span>Research AI</span>
              </div>
              <div className="agent-num-label">02</div>
              <h1 className="agent-hero-heading research">RESEARCH AI</h1>
              <p className="agent-hero-tagline">Turn complex papers<br />into useful intelligence.</p>
            </motion.div>
            <motion.div className="agent-hero-stats" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
              <div className="agent-stat"><span className="agent-stat-value">412</span><span className="agent-stat-label">Papers Analyzed</span></div>
              <div className="agent-stat"><span className="agent-stat-value">97%</span><span className="agent-stat-label">Summary Accuracy</span></div>
              <div className="agent-stat"><span className="agent-stat-value">24s</span><span className="agent-stat-label">Avg. Analysis Time</span></div>
            </motion.div>
          </div>
        </div>

        <div className="agent-workspace">

          {/* Upload + paper list */}
          <motion.div className="workspace-panel" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <div className="workspace-panel-header">
              <span className="workspace-panel-label">Upload Research Paper</span>
            </div>
            <div className={`upload-zone research-upload ${uploaded ? 'uploaded' : ''}`} onClick={handleUpload}>
              {uploading ? (
                <div className="upload-loading">
                  <div className="upload-spinner research-spinner" />
                  <span>Parsing document structure...</span>
                </div>
              ) : uploaded ? (
                <div className="upload-success">
                  <div className="upload-success-icon research-icon">✓</div>
                  <span>attention_is_all_you_need.pdf</span>
                  <span className="upload-success-sub">12 pages · Uploaded</span>
                </div>
              ) : (
                <div className="upload-prompt">
                  <div className="upload-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                    </svg>
                  </div>
                  <span>Upload PDF research paper</span>
                  <span className="upload-sub">arXiv, journal articles, reports</span>
                </div>
              )}
            </div>

            <div className="workspace-panel-header" style={{ marginTop: '24px' }}>
              <span className="workspace-panel-label">Recent Papers</span>
              <span className="panel-header-count">{PAPERS.length} papers</span>
            </div>
            <div className="paper-list">
              {PAPERS.map((p, i) => (
                <button
                  key={p.id}
                  className={`paper-item ${activePaper === i ? 'active' : ''}`}
                  onClick={() => setActivePaper(i)}
                >
                  <div className="paper-item-meta">
                    <span className="paper-topic">{p.topic}</span>
                    <span className={`paper-quality ${p.quality.toLowerCase()}`}>{p.quality}</span>
                  </div>
                  <div className="paper-title">{p.title}</div>
                  <div className="paper-authors">{p.authors} · {p.year}</div>
                </button>
              ))}
            </div>
          </motion.div>

          {/* Analysis results */}
          <motion.div className="workspace-panel wide-panel" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <AnimatePresence mode="wait">
              <motion.div
                key={activePaper}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.35 }}
              >
                <div className="workspace-panel-header">
                  <span className="workspace-panel-label">AI Content Analysis</span>
                  <div className="relevance-indicator">
                    <span className="relevance-label">Topic Relevance</span>
                    <span className="relevance-value">{paper.relevance}%</span>
                  </div>
                </div>

                <div className="paper-detail-header">
                  <h2 className="paper-detail-title">{paper.title}</h2>
                  <p className="paper-detail-meta">{paper.authors} · {paper.year} · {paper.references} References</p>
                </div>

                <div className="analysis-sections">
                  <div className="analysis-section">
                    <div className="workspace-field-label">Summary</div>
                    <p className="analysis-text">{paper.summary}</p>
                  </div>

                  <div className="analysis-section">
                    <div className="workspace-field-label">Key Findings</div>
                    <div className="findings-list">
                      {paper.keyFindings.map((f, i) => (
                        <motion.div
                          key={i}
                          className="finding-item"
                          initial={{ opacity: 0, x: -12 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.1 }}
                        >
                          <span className="finding-num">0{i + 1}</span>
                          <span className="finding-text">{f}</span>
                        </motion.div>
                      ))}
                    </div>
                  </div>

                  <div className="analysis-section">
                    <div className="workspace-field-label">Research Quality</div>
                    <div className="quality-display">
                      <span className={`quality-badge ${paper.quality.toLowerCase()}`}>{paper.quality}</span>
                      <p className="quality-sub">Peer-reviewed · Highly cited · Foundational contribution</p>
                    </div>
                  </div>
                </div>
              </motion.div>
            </AnimatePresence>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
