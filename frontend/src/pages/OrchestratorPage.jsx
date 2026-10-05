import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../context/AuthContext';
import Navigation from '../components/Navigation';
import { useAgents } from '../hooks/useAgents';
import { useActivity } from '../hooks/useActivity';

const SUGGESTIONS = [
  'Find candidates for the React Developer role',
  'Summarize the latest research paper on LLMs',
  'What is our employee leave policy?',
  'Schedule a meeting with the HR team for Friday',
  'Show this week\'s AI activity report',
];

function OrchestratorDashboard({ permissions, onAgentClick, isRouting, routingTarget, agents, activities }) {
  return (
    <div className="orchestrator-dashboard">
      <div className="dashboard-section">
        <div className="dashboard-header-flex">
          <h2 className="dashboard-heading">System Status</h2>
          <span className="status-badge">All Systems Operational</span>
        </div>
        <div className="agent-status-grid">
          {agents.map(agent => {
            const hasAccess = permissions[agent.id] !== 'none';
            const isTarget = isRouting && routingTarget?.id === agent.id;
            return (
              <button 
                key={agent.id} 
                className={`status-card ${!hasAccess ? 'locked' : ''} ${isTarget ? 'routing-target' : ''}`}
                onClick={() => hasAccess ? onAgentClick(agent) : null}
                style={{ '--agent-color': agent.colorLight || agent.color }}
              >
                <div className="status-card-header">
                  <div className="status-indicator">
                    <span className="status-dot" />
                    <span className="status-name">{agent.short}</span>
                  </div>
                  {!hasAccess && <span className="status-lock">⚿</span>}
                </div>
                <div className="status-card-desc">{agent.description}</div>
              </button>
            )
          })}
        </div>
      </div>

      <div className="dashboard-section">
        <h2 className="dashboard-heading">Recent Activity</h2>
        <div className="activity-feed">
          <AnimatePresence>
            {isRouting && routingTarget && (
              <motion.div 
                className="activity-item routing"
                initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                animate={{ opacity: 1, height: 'auto', marginBottom: 12 }}
                exit={{ opacity: 0, height: 0, marginBottom: 0 }}
              >
                <div className="activity-indicator pulse" style={{ background: routingTarget.colorLight || routingTarget.color }} />
                <div className="activity-content">
                  <div className="activity-task">Routing request to {routingTarget.name}...</div>
                  <div className="activity-meta">
                    <span className="activity-status" style={{ color: routingTarget.colorLight || routingTarget.color }}>PROCESSING</span>
                    <span className="activity-time">Now</span>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          {activities.filter(item => permissions[item.agent] !== 'none').map((item, i) => {
            const agent = agents.find(a => a.id === item.agent);
            if (!agent) return null;
            return (
              <motion.div 
                key={item.id} 
                className="activity-item"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 + (i * 0.1) }}
              >
                <div className="activity-indicator" style={{ background: item.status === 'processing' ? (agent.colorLight || agent.color) : 'rgba(245,244,240,0.15)' }} />
                <div className="activity-content">
                  <div className="activity-task">{item.task}</div>
                  <div className="activity-meta">
                    <span className="activity-agent">{agent.short}</span>
                    <span className="activity-time">{item.time}</span>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  );
}

export default function OrchestratorPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [isRouting, setIsRouting] = useState(false);
  const [routingTarget, setRoutingTarget] = useState(null);
  const inputRef = useRef(null);

  const { agents, isLoading: agentsLoading } = useAgents();
  const { activities, isLoading: activityLoading } = useActivity();

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  const permissions = {};
  if (agents) {
    agents.forEach(a => {
      permissions[a.id] = user?.permissions?.[a.id] || 'none';
    });
  }

  const detectAgent = (q) => {
    if (!agents || agents.length === 0) return null;
    const lower = q.toLowerCase();
    if (lower.includes('candidat') || lower.includes('hir') || lower.includes('recruit') || lower.includes('role') || lower.includes('resume')) {
      return agents.find(a => a.id === 'hiring');
    }
    if (lower.includes('paper') || lower.includes('research') || lower.includes('study') || lower.includes('summar')) {
      return agents.find(a => a.id === 'research');
    }
    if (lower.includes('policy') || lower.includes('leave') || lower.includes('handbook') || lower.includes('document') || lower.includes('know')) {
      return agents.find(a => a.id === 'knowledge');
    }
    if (lower.includes('meeting') || lower.includes('schedul') || lower.includes('calendar') || lower.includes('team')) {
      return agents.find(a => a.id === 'communication');
    }
    if (lower.includes('activ') || lower.includes('insight') || lower.includes('analytic') || lower.includes('report') || lower.includes('week')) {
      return agents.find(a => a.id === 'insights');
    }
    return agents[0];
  };

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!query.trim() || isRouting || agentsLoading) return;
    const target = detectAgent(query);
    if (!target) return;
    
    setRoutingTarget(target);
    setIsRouting(true);
    
    setTimeout(() => {
      if (permissions[target.id] !== 'none') {
        navigate(target.path);
      } else {
        setIsRouting(false); 
        setQuery('');
      }
    }, 1500);
  };

  const handleSuggestion = (s) => {
    setQuery(s);
    inputRef.current?.focus();
  };

  const handleAgentClick = (agent) => {
    if (permissions[agent.id] === 'none' || isRouting) return;
    navigate(agent.path);
  };

  const isLoading = agentsLoading || activityLoading;

  return (
    <div className="orchestrator-page">
      <Navigation />

      <main className="orchestrator-main">
        <motion.div
          className="orchestrator-topbar"
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="orchestrator-greeting">
            <span className="orchestrator-time-label">{greeting},</span>
            <span className="orchestrator-user-name">{user?.name}</span>
          </div>
          <div className="orchestrator-meta-strip">
            <span className="orchestrator-meta-chip">
              <span className="meta-chip-key">Role</span>
              <span className="meta-chip-val">{user?.role}</span>
            </span>
            <span className="orchestrator-meta-chip">
              <span className="meta-chip-key">Access</span>
              <span className="meta-chip-val">{user?.accessLevel}</span>
            </span>
            <span className="orchestrator-meta-chip">
              <span className="meta-chip-key">Org</span>
              <span className="meta-chip-val">{user?.organization}</span>
            </span>
          </div>
        </motion.div>

        <div className="orchestrator-body">
          <div className="orchestrator-left">
            <motion.div
              className="orchestrator-hero"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.1 }}
            >
              <h1 className="orchestrator-hero-heading">
                WHAT CAN WE<br />
                <span className="orchestrator-hero-accent">GET DONE?</span>
              </h1>
              <p className="orchestrator-hero-sub">
                The orchestrator routes your requests to the right AI agent automatically.
              </p>
            </motion.div>

            <motion.form
              className="orchestrator-command"
              onSubmit={handleSubmit}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
            >
              <div className="command-input-wrap">
                <div className="command-icon">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="8" />
                    <path d="m21 21-4.35-4.35" />
                  </svg>
                </div>
                <input
                  ref={inputRef}
                  type="text"
                  className="command-input"
                  placeholder="Ask the workspace anything..."
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  disabled={isRouting || isLoading}
                />
                <button type="submit" className="command-submit" disabled={!query.trim() || isRouting || isLoading}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="m5 12 14 0M12 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
              <div className="command-suggestions">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    className="command-suggestion"
                    onClick={() => handleSuggestion(s)}
                    disabled={isRouting || isLoading}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </motion.form>
          </div>

          <motion.div
            className="orchestrator-right"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.3 }}
          >
            {isLoading ? (
              <div className="loading-state" style={{ padding: '40px', color: 'rgba(255,255,255,0.4)', fontFamily: 'JetBrains Mono', fontSize: '12px' }}>
                INITIALIZING SUBSYSTEMS...
              </div>
            ) : (
              <OrchestratorDashboard
                permissions={permissions}
                onAgentClick={handleAgentClick}
                isRouting={isRouting}
                routingTarget={routingTarget}
                agents={agents}
                activities={activities}
              />
            )}
          </motion.div>
        </div>
      </main>
    </div>
  );
}
