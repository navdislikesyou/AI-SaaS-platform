import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Terminal,
  Cpu,
  BookOpen,
  Zap,
  BarChart3,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  Activity,
  CornerDownLeft,
} from 'lucide-react';
import Navigation from '../components/Navigation';
import { useAgents } from '../hooks/useAgents';
import { useSystemHealth } from '../hooks/useSystemHealth';

const TEMPLATES = [
  {
    label: 'Leave Policy Query',
    prompt: 'What is our employee leave policy?',
    agent: 'knowledge',
    category: 'RAG Q&A',
  },
  {
    label: 'Sprint Action Plan',
    prompt: 'Draft sprint retro action list for team deliverables',
    agent: 'automation',
    category: 'Action Draft',
  },
  {
    label: 'Revenue Analytics',
    prompt: 'Compute quarterly performance KPIs and utilization metrics',
    agent: 'performance',
    category: 'Data Analytics',
  },
  {
    label: 'Remote Work Framework',
    prompt: 'How many remote work days are permitted per week?',
    agent: 'knowledge',
    category: 'Policy Search',
  },
];

const DISPATCH_HISTORY = [
  {
    id: 'req_01',
    agent: 'knowledge',
    op: 'query',
    status: '503',
    latency: '3.1ms',
    time: '2m ago',
    desc: 'Knowledge query: employee handbook index',
  },
  {
    id: 'req_02',
    agent: 'automation',
    op: 'draft_action',
    status: '503',
    latency: '2.4ms',
    time: '14m ago',
    desc: 'Action drafted: leadership sync agenda',
  },
  {
    id: 'req_03',
    agent: 'performance',
    op: 'compute_kpis',
    status: '503',
    latency: '4.8ms',
    time: '1h ago',
    desc: 'Statistical aggregation: agent_utilization',
  },
];

export default function OrchestratorPage() {
  const navigate = useNavigate();
  const inputRef = useRef(null);

  const [query, setQuery] = useState('');
  const [isRouting, setIsRouting] = useState(false);
  const [routingTarget, setRoutingTarget] = useState(null);

  const { agents } = useAgents();
  const { isOnline, health } = useSystemHealth();

  const detectAgent = (q) => {
    if (!agents || agents.length === 0) return null;
    const lower = q.toLowerCase();
    if (lower.includes('policy') || lower.includes('leave') || lower.includes('handbook') || lower.includes('document') || lower.includes('know')) {
      return agents.find((a) => a.id === 'knowledge') || agents[0];
    }
    if (lower.includes('action') || lower.includes('draft') || lower.includes('meeting') || lower.includes('schedul') || lower.includes('task')) {
      return agents.find((a) => a.id === 'automation') || agents[0];
    }
    if (lower.includes('kpi') || lower.includes('metric') || lower.includes('perform') || lower.includes('stat') || lower.includes('dataset') || lower.includes('trend')) {
      return agents.find((a) => a.id === 'performance') || agents[0];
    }
    return agents.find((a) => a.id === 'knowledge') || agents[0];
  };

  const currentDetected = query.trim() ? detectAgent(query) : null;

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!query.trim() || isRouting) return;
    const target = detectAgent(query);
    if (!target) return;

    setRoutingTarget(target);
    setIsRouting(true);

    setTimeout(() => {
      navigate(target.path, { state: { query } });
    }, 800);
  };

  const handleTemplate = (tmpl) => {
    setQuery(tmpl.prompt);
    inputRef.current?.focus();
  };

  const getAgentIcon = (id) => {
    switch (id) {
      case 'knowledge':
        return <BookOpen size={18} color="#E8FF72" />;
      case 'automation':
        return <Zap size={18} color="#4A9DC4" />;
      case 'performance':
        return <BarChart3 size={18} color="#FF5A00" />;
      default:
        return <Cpu size={18} color="#ffffff" />;
    }
  };

  return (
    <div className="saas-workbench">
      <Navigation />

      <main className="saas-main-container">
        {/* Top App Bar */}
        <div className="saas-topbar">
          <div className="saas-breadcrumb">
            <span className="saas-breadcrumb-item">Workspace</span>
            <span className="saas-breadcrumb-sep">/</span>
            <span className="saas-breadcrumb-active">AI Command Center</span>
          </div>

          <div className="saas-topbar-actions">
            <div className={`saas-status-chip ${isOnline ? 'online' : 'offline'}`}>
              <div className="saas-pulse-dot" />
              <span>{isOnline ? 'AI Assistants Active' : 'Connecting...'}</span>
            </div>
          </div>
        </div>

        {/* Page Body */}
        <div className="saas-page-body">
          {/* Header */}
          <div className="saas-page-header">
            <div className="saas-page-title-wrap">
              <h1 className="saas-page-title">AI Command Center</h1>
              <p className="saas-page-subtitle">
                Ask a question, request a draft, or analyze metrics. The system will automatically select the right AI assistant for you.
              </p>
            </div>
          </div>

          {/* Omnibox Command Dispatcher */}
          <form className="saas-omnibox" onSubmit={handleSubmit}>
            <div className="saas-omnibox-input-row">
              <Terminal size={20} color="rgba(255,255,255,0.4)" />
              <input
                ref={inputRef}
                type="text"
                className="saas-omnibox-input"
                placeholder="Ask anything (e.g. 'What is our leave policy?', 'Draft sprint review agenda', 'Show Q3 performance')..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isRouting}
              />
              <div className="saas-omnibox-actions">
                {currentDetected && (
                  <span
                    className="saas-target-chip"
                    style={{
                      background: `${currentDetected.color}20`,
                      color: currentDetected.color,
                      border: `1px solid ${currentDetected.color}40`,
                    }}
                  >
                    <Sparkles size={11} />
                    <span>Auto-Routing: {currentDetected.name}</span>
                  </span>
                )}
                <button
                  type="submit"
                  className="saas-btn saas-btn-primary"
                  disabled={!query.trim() || isRouting}
                  style={{ padding: '6px 16px', fontSize: '0.82rem' }}
                >
                  {isRouting ? (
                    'Consulting...'
                  ) : (
                    <>
                      <span>Ask Assistant</span>
                      <CornerDownLeft size={13} />
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Template Chips */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '14px', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', alignSelf: 'center', fontFamily: 'JetBrains Mono' }}>
                TEMPLATES:
              </span>
              {TEMPLATES.map((tmpl, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleTemplate(tmpl)}
                  style={{
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: '5px',
                    padding: '4px 10px',
                    fontSize: '0.72rem',
                    color: '#d4d4d8',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.25)')}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)')}
                >
                  {tmpl.label}
                </button>
              ))}
            </div>
          </form>

          {/* Grid: Agent Matrix on Left, Live Telemetry on Right */}
          <div className="saas-workbench-grid">
            {/* Left: Connected Agent Fleet */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'JetBrains Mono' }}>
                  Registered Agent Fleet (FastAPI Adapters)
                </span>
                <span style={{ fontSize: '0.7rem', color: '#E8FF72', fontFamily: 'JetBrains Mono' }}>
                  3 / 3 Adapters Active
                </span>
              </div>

              {agents.filter((a) => a.isBackend).map((agent) => (
                <div key={agent.id} className="saas-card" style={{ transition: 'border-color 0.2s' }}>
                  <div className="saas-card-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div
                        style={{
                          width: '32px',
                          height: '32px',
                          borderRadius: '8px',
                          background: `${agent.color}15`,
                          border: `1px solid ${agent.color}30`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {getAgentIcon(agent.id)}
                      </div>
                      <div>
                        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fafafa', fontFamily: 'Syne' }}>
                          {agent.name}
                        </div>
                        <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.4)', fontFamily: 'JetBrains Mono' }}>
                          backend/app/agents/adapters/{agent.id}.py
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span
                        style={{
                          fontFamily: 'JetBrains Mono',
                          fontSize: '0.62rem',
                          padding: '3px 8px',
                          borderRadius: '4px',
                          background: 'rgba(232,255,114,0.1)',
                          color: '#E8FF72',
                          border: '1px solid rgba(232,255,114,0.25)',
                          textTransform: 'uppercase',
                        }}
                      >
                        SEAM CONNECTED
                      </span>
                      <button
                        className="saas-btn saas-btn-secondary"
                        onClick={() => navigate(agent.path)}
                        style={{ padding: '4px 10px', fontSize: '0.72rem' }}
                      >
                        <span>Workspace</span>
                        <ArrowRight size={12} />
                      </button>
                    </div>
                  </div>

                  <div className="saas-card-body">
                    <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.5, marginBottom: '12px' }}>
                      {agent.description}
                    </p>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {agent.capabilities.map((cap) => (
                        <span
                          key={cap}
                          style={{
                            fontFamily: 'JetBrains Mono',
                            fontSize: '0.68rem',
                            padding: '3px 8px',
                            borderRadius: '4px',
                            background: 'rgba(255,255,255,0.04)',
                            border: '1px solid rgba(255,255,255,0.08)',
                            color: '#d4d4d8',
                          }}
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Right: Real-time Telemetry & Seam Monitor */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Platform Security & Status
              </span>

              {/* Security & Reliability Card */}
              <div className="saas-card">
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <ShieldCheck size={16} color="#E8FF72" />
                    <span>Workspace Protection</span>
                  </div>
                </div>
                <div className="saas-card-body" style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.45)' }}>Access Control:</span>
                    <span style={{ color: '#10B981' }}>Isolated & Secure</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.45)' }}>Data Privacy:</span>
                    <span style={{ color: '#f4f4f5' }}>Zero External Training</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.45)' }}>Response Engine:</span>
                    <span style={{ color: '#E8FF72' }}>Instant Async</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'rgba(255,255,255,0.45)' }}>Platform Availability:</span>
                    <span style={{ color: '#10B981' }}>99.9% Uptime</span>
                  </div>
                </div>
              </div>

              {/* Event Stream Card */}
              <div className="saas-card">
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <Activity size={16} color="#4A9DC4" />
                    <span>Recent Activity</span>
                  </div>
                </div>
                <div className="saas-card-body" style={{ padding: '8px 14px' }}>
                  {DISPATCH_HISTORY.map((item) => (
                    <div
                      key={item.id}
                      style={{
                        padding: '10px 0',
                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                        display: 'flex',
                        alignItems: 'flex-start',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f4f4f5', textTransform: 'capitalize' }}>
                            {item.agent} Assistant
                          </span>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
                          {item.desc}
                        </div>
                      </div>

                      <div style={{ textAlign: 'right' }}>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            background: 'rgba(16, 185, 129, 0.12)',
                            color: '#10B981',
                          }}
                        >
                          Completed
                        </span>
                        <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.35)', marginTop: '2px' }}>
                          {item.time}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
