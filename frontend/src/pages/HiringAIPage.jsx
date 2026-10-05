import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import Navigation from '../components/Navigation';

const CANDIDATES = [
  {
    name: 'Alex Johnson',
    role: 'Senior React Developer',
    match: 92,
    skills: ['React', 'Node.js', 'PostgreSQL', 'TypeScript'],
    experience: '6 years',
    recommendation: 'Strong match. Technical profile aligns with role requirements. Exceptional React expertise and full-stack breadth.',
    status: 'top',
  },
  {
    name: 'Priya Mehta',
    role: 'Senior React Developer',
    match: 87,
    skills: ['React', 'GraphQL', 'MongoDB', 'AWS'],
    experience: '5 years',
    recommendation: 'Good match. Strong frontend skills with cloud experience. Slightly less backend depth.',
    status: 'good',
  },
  {
    name: 'Daniel Torres',
    role: 'Senior React Developer',
    match: 74,
    skills: ['React', 'Vue.js', 'MySQL', 'Docker'],
    experience: '4 years',
    recommendation: 'Moderate match. Solid React foundation but lacks PostgreSQL experience required for this role.',
    status: 'moderate',
  },
];

function MatchBar({ value }) {
  return (
    <div className="match-bar-wrap">
      <div className="match-bar-track">
        <motion.div
          className="match-bar-fill"
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 1, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
          style={{
            background: value >= 85 ? '#E8FF72' : value >= 75 ? '#FF5A00' : 'rgba(255,255,255,0.3)'
          }}
        />
      </div>
      <span className="match-bar-value">{value}%</span>
    </div>
  );
}

export default function HiringAIPage() {
  const navigate = useNavigate();
  const [activeCandidate, setActiveCandidate] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [jobDesc, setJobDesc] = useState('');
  const [analyzed, setAnalyzed] = useState(false);

  const handleUpload = () => {
    setUploading(true);
    setTimeout(() => { setUploading(false); setUploaded(true); }, 1800);
  };

  const handleAnalyze = () => {
    if (!uploaded && !analyzed) return;
    setAnalyzed(true);
  };

  const candidate = CANDIDATES[activeCandidate];

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main">

        {/* Agent hero */}
        <div className="agent-hero hiring-hero">
          <div className="agent-hero-inner">
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9 }}
            >
              <div className="agent-hero-breadcrumb">
                <button onClick={() => navigate('/agents')} className="breadcrumb-back">AI Agents</button>
                <span>→</span>
                <span>Hiring AI</span>
              </div>
              <div className="agent-num-label">01</div>
              <h1 className="agent-hero-heading">HIRING AI</h1>
              <p className="agent-hero-tagline">
                Find the right people,<br />without the manual work.
              </p>
            </motion.div>

            <motion.div
              className="agent-hero-stats"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
            >
              <div className="agent-stat">
                <span className="agent-stat-value">2,847</span>
                <span className="agent-stat-label">Resumes Analyzed</span>
              </div>
              <div className="agent-stat">
                <span className="agent-stat-value">94%</span>
                <span className="agent-stat-label">Match Accuracy</span>
              </div>
              <div className="agent-stat">
                <span className="agent-stat-value">68h</span>
                <span className="agent-stat-label">Saved This Month</span>
              </div>
            </motion.div>
          </div>
        </div>

        {/* Workspace */}
        <div className="agent-workspace">

          {/* Upload panel */}
          <motion.div
            className="workspace-panel"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <div className="workspace-panel-header">
              <span className="workspace-panel-label">Upload Resume</span>
            </div>
            <div
              className={`upload-zone ${uploaded ? 'uploaded' : ''}`}
              onClick={handleUpload}
            >
              {uploading ? (
                <div className="upload-loading">
                  <div className="upload-spinner" />
                  <span>Analyzing resume...</span>
                </div>
              ) : uploaded ? (
                <div className="upload-success">
                  <div className="upload-success-icon">✓</div>
                  <span>alex_johnson_resume.pdf</span>
                  <span className="upload-success-sub">3 pages · 142KB</span>
                </div>
              ) : (
                <div className="upload-prompt">
                  <div className="upload-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="17 8 12 3 7 8"/>
                      <line x1="12" y1="3" x2="12" y2="15"/>
                    </svg>
                  </div>
                  <span>Drop resume or click to upload</span>
                  <span className="upload-sub">PDF, DOCX · Max 10MB</span>
                </div>
              )}
            </div>

            <div className="workspace-panel-header" style={{ marginTop: '24px' }}>
              <span className="workspace-panel-label">Job Description</span>
            </div>
            <textarea
              className="jd-textarea"
              placeholder="Paste job description or requirements..."
              value={jobDesc}
              onChange={e => setJobDesc(e.target.value)}
              rows={4}
            />

            <button
              className={`analyze-btn ${uploaded ? 'active' : ''}`}
              onClick={handleAnalyze}
              disabled={!uploaded}
            >
              Analyze Candidates →
            </button>
          </motion.div>

          {/* Candidates panel */}
          <motion.div
            className="workspace-panel"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <div className="workspace-panel-header">
              <span className="workspace-panel-label">Candidate Analysis</span>
              <span className="panel-header-count">{CANDIDATES.length} candidates</span>
            </div>

            <div className="candidate-list">
              {CANDIDATES.map((c, i) => (
                <button
                  key={i}
                  className={`candidate-item ${activeCandidate === i ? 'active' : ''} ${c.status}`}
                  onClick={() => setActiveCandidate(i)}
                >
                  <div className="candidate-avatar">
                    {c.name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="candidate-info">
                    <span className="candidate-name">{c.name}</span>
                    <span className="candidate-role">{c.experience} experience</span>
                  </div>
                  <div className="candidate-match-badge" style={{
                    color: c.match >= 85 ? '#E8FF72' : c.match >= 75 ? '#FF5A00' : 'rgba(255,255,255,0.4)'
                  }}>
                    {c.match}%
                  </div>
                </button>
              ))}
            </div>
          </motion.div>

          {/* Candidate detail */}
          <motion.div
            className="workspace-panel candidate-detail-panel"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <AnimatePresence mode="wait">
              <motion.div
                key={activeCandidate}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.3 }}
              >
                <div className="workspace-panel-header">
                  <span className="workspace-panel-label">Candidate Match</span>
                  <span className={`match-status ${candidate.status}`}>
                    {candidate.status === 'top' ? 'Top Match' : candidate.status === 'good' ? 'Good Match' : 'Review'}
                  </span>
                </div>

                <div className="candidate-profile">
                  <div className="candidate-profile-top">
                    <div className="candidate-profile-avatar large">
                      {candidate.name.split(' ').map(n => n[0]).join('')}
                    </div>
                    <div>
                      <h3 className="candidate-profile-name">{candidate.name}</h3>
                      <p className="candidate-profile-exp">{candidate.experience} · {candidate.role}</p>
                    </div>
                  </div>

                  <div className="candidate-match-section">
                    <div className="workspace-field-label">Match Score</div>
                    <MatchBar value={candidate.match} />
                  </div>

                  <div className="candidate-skills-section">
                    <div className="workspace-field-label">Skills</div>
                    <div className="candidate-skills">
                      {candidate.skills.map(s => (
                        <span key={s} className="skill-tag">{s}</span>
                      ))}
                    </div>
                  </div>

                  <div className="ai-recommendation">
                    <div className="ai-rec-label">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 8v4l3 3"/>
                      </svg>
                      AI Recommendation
                    </div>
                    <p className="ai-rec-text">{candidate.recommendation}</p>
                  </div>

                  <div className="candidate-actions">
                    <button className="cand-action-btn primary">Schedule Interview</button>
                    <button className="cand-action-btn secondary">View Full Profile</button>
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
