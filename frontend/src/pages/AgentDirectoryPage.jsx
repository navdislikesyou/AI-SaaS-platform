import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import Navigation from '../components/Navigation';

const AGENTS = [
  {
    id: 'hiring',
    num: '01',
    name: 'HIRING AI',
    tagline: 'Find the right people, without the manual work.',
    description: 'AI-powered candidate analysis, resume screening, job matching, and intelligent recruitment workflows.',
    capabilities: ['Resume Analysis', 'Candidate Matching', 'Skill Assessment', 'AI Recommendations', 'Pipeline Tracking'],
    path: '/agents/hiring',
    color: '#FF5A00',
    bg: '#0d0400',
  },
  {
    id: 'research',
    num: '02',
    name: 'RESEARCH AI',
    tagline: 'Turn complex papers into useful intelligence.',
    description: 'Upload research papers and extract summaries, key findings, methodologies, and topic relevance scores automatically.',
    capabilities: ['Paper Analysis', 'Topic Relevance', 'Key Findings', 'Research Quality Score', 'Reference Mapping'],
    path: '/agents/research',
    color: '#f5f4f0',
    bg: '#000414',
  },
  {
    id: 'knowledge',
    num: '03',
    name: 'KNOWLEDGE AI',
    tagline: 'Ask your organization anything.',
    description: 'A RAG-powered enterprise knowledge system. Query documents, handbooks, policies, and internal knowledge bases instantly.',
    capabilities: ['Document Retrieval', 'Policy Search', 'Context-Aware Answers', 'Source Citations', 'Permission-Based Access'],
    path: '/agents/knowledge',
    color: '#E8FF72',
    bg: '#090a00',
  },
  {
    id: 'communication',
    num: '04',
    name: 'COMMUNICATION AI',
    tagline: 'Turn communication into automation.',
    description: 'Intelligent scheduling, meeting automation, participant coordination, and post-meeting intelligence generation.',
    capabilities: ['Meeting Scheduling', 'Link Generation', 'Participant Notification', 'Reminder Automation', 'MoM Generation'],
    path: '/agents/communication',
    color: '#4a9dc4',
    bg: '#000a0d',
  },
  {
    id: 'insights',
    // num: '05',
    name: 'INSIGHTS AI',
    tagline: 'Understand how your organization works.',
    description: 'Editorial analytics and organizational intelligence — AI usage metrics, workflow performance, agent utilization, and time savings.',
    capabilities: ['Usage Analytics', 'Agent Performance', 'Workflow Activity', 'Time Saved Metrics', 'Team Intelligence'],
    path: '/agents/insights',
    color: '#FFFBE8',
    bg: '#0a0a08',
  },
];

export default function AgentDirectoryPage() {
  const { canAccess, accessLevel } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="agdir-page">
      <Navigation />
      <main className="agdir-main">
        {/* Hero */}
        <motion.div
          className="agdir-hero"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9 }}
        >
          <div className="agdir-hero-label">AI Agents</div>
          <h1 className="agdir-hero-heading">YOUR AI<br />WORKFORCE</h1>
          <p className="agdir-hero-sub">Specialized intelligence for specialized work.</p>
        </motion.div>

        <div className="agdir-divider" />

        {/* Agent blocks */}
        <div className="agdir-list">
          {AGENTS.map((agent, i) => {
            const hasAccess = canAccess(agent.id);
            const level = accessLevel(agent.id);
            return (
              <motion.div
                key={agent.id}
                className={`agdir-block ${!hasAccess ? 'locked' : ''}`}
                initial={{ opacity: 0, y: 40 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: i * 0.1 }}
                style={{ '--agent-color': agent.color, '--agent-bg': agent.bg }}
              >
                <div className="agdir-block-inner">
                  {/* Left: Number + meta */}
                  <div className="agdir-block-meta">
                    <span className="agdir-block-num">{agent.num}</span>
                    {!hasAccess && (
                      <div className="agdir-block-locked-label">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                        </svg>
                        Restricted
                      </div>
                    )}
                    {level === 'limited' && (
                      <div className="agdir-block-limited-label">Limited</div>
                    )}
                  </div>

                  {/* Center: Content */}
                  <div className="agdir-block-content">
                    <h2 className="agdir-block-name">{agent.name}</h2>
                    <p className="agdir-block-tagline">{agent.tagline}</p>
                    <p className="agdir-block-desc">{agent.description}</p>

                    <div className="agdir-capabilities">
                      {agent.capabilities.map(cap => (
                        <span key={cap} className="agdir-cap-tag">{cap}</span>
                      ))}
                    </div>
                  </div>

                  {/* Right: CTA or locked */}
                  <div className="agdir-block-action">
                    {hasAccess ? (
                      <motion.button
                        className="agdir-cta"
                        onClick={() => navigate(agent.path)}
                        whileHover={{ x: 4 }}
                        transition={{ duration: 0.2 }}
                      >
                        OPEN WORKSPACE
                        <span className="agdir-cta-arrow">→</span>
                      </motion.button>
                    ) : (
                      <div className="agdir-locked-state">
                        <p className="agdir-locked-msg">Access Restricted</p>
                        <p className="agdir-locked-sub">You don't have permission to access this workspace.</p>
                        <button className="agdir-request-btn">Request Access</button>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
