import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Cpu,
  BookOpen,
  Zap,
  BarChart3,
  Search,
  ArrowRight,
} from 'lucide-react';
import Navigation from '../components/Navigation';
import { useAgents } from '../hooks/useAgents';

export default function AgentDirectoryPage() {
  const navigate = useNavigate();
  const { agents, isLoading } = useAgents();

  const [filter, setFilter] = useState('all'); // 'all', 'backend', 'roadmap'
  const [searchQuery, setSearchQuery] = useState('');

  const filteredAgents = agents.filter((agent) => {
    if (filter === 'backend' && !agent.isBackend) return false;
    if (filter === 'roadmap' && !agent.isRoadmap) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = agent.name.toLowerCase().includes(q);
      const matchDesc = agent.description?.toLowerCase().includes(q);
      const matchCap = agent.capabilities?.some((c) => c.toLowerCase().includes(q));
      return matchName || matchDesc || matchCap;
    }
    return true;
  });

  const getAgentIcon = (id, color) => {
    switch (id) {
      case 'knowledge':
        return <BookOpen size={20} color={color} />;
      case 'automation':
        return <Zap size={20} color={color} />;
      case 'performance':
        return <BarChart3 size={20} color={color} />;
      default:
        return <Cpu size={20} color={color} />;
    }
  };

  return (
    <div className="saas-workbench">
      <Navigation />

      <main className="saas-main-container">
        {/* Topbar */}
        <div className="saas-topbar">
          <div className="saas-breadcrumb">
            <span className="saas-breadcrumb-item">Workspace</span>
            <span className="saas-breadcrumb-sep">/</span>
            <span className="saas-breadcrumb-active">AI Assistants</span>
          </div>

          <div className="saas-topbar-actions">
            <span
              style={{
                fontSize: '0.75rem',
                padding: '4px 10px',
                borderRadius: '4px',
                background: 'rgba(255,255,255,0.05)',
                color: '#f4f4f5',
                border: '1px solid rgba(255,255,255,0.1)',
              }}
            >
              Total Assistants: {agents.length}
            </span>
          </div>
        </div>

        {/* Page Body */}
        <div className="saas-page-body">
          {/* Header */}
          <div className="saas-page-header">
            <div className="saas-page-title-wrap">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Cpu size={22} color="#E8FF72" />
                <h1 className="saas-page-title">AI Assistants Catalog</h1>
              </div>
              <p className="saas-page-subtitle">
                Explore specialized AI assistants available for your team to automate tasks, answer questions, and analyze data.
              </p>
            </div>
          </div>

          {/* Filter & Search Bar */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', marginBottom: '20px', flexWrap: 'wrap' }}>
            <div className="saas-tabs-bar" style={{ marginBottom: 0, borderBottom: 'none' }}>
              <button
                className={`saas-tab-btn ${filter === 'all' ? 'active' : ''}`}
                onClick={() => setFilter('all')}
              >
                All Assistants ({agents.length})
              </button>
              <button
                className={`saas-tab-btn ${filter === 'backend' ? 'active' : ''}`}
                onClick={() => setFilter('backend')}
              >
                Active Now (3)
              </button>
              <button
                className={`saas-tab-btn ${filter === 'roadmap' ? 'active' : ''}`}
                onClick={() => setFilter('roadmap')}
              >
                Coming Soon (2)
              </button>
            </div>

            <div style={{ position: 'relative', width: '280px' }}>
              <Search size={14} color="rgba(255,255,255,0.4)" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="text"
                className="saas-input"
                placeholder="Search assistant or feature..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ paddingLeft: '34px', fontSize: '0.8rem', padding: '7px 12px 7px 34px' }}
              />
            </div>
          </div>

          {/* Loading state */}
          {isLoading && (
            <div style={{ padding: '60px', textAlign: 'center', color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem' }}>
              Loading AI Assistants...
            </div>
          )}

          {/* Cards Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: '16px' }}>
            {filteredAgents.map((agent) => (
              <div
                key={agent.id}
                className="saas-card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  transition: 'all 0.2s ease',
                  border: '1px solid rgba(255,255,255,0.08)',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)')}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)')}
              >
                <div>
                  <div className="saas-card-header">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div
                        style={{
                          width: '34px',
                          height: '34px',
                          borderRadius: '8px',
                          background: `${agent.color}15`,
                          border: `1px solid ${agent.color}30`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {getAgentIcon(agent.id, agent.color)}
                      </div>
                      <div>
                        <div style={{ fontSize: '0.92rem', fontWeight: 600, color: '#fafafa', fontFamily: 'Syne' }}>
                          {agent.name}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.45)' }}>
                          {agent.isBackend ? 'Active in Workspace' : 'Coming in Future Update'}
                        </div>
                      </div>
                    </div>

                    <div>
                      {agent.isBackend ? (
                        <span
                          style={{
                            fontSize: '0.65rem',
                            padding: '3px 8px',
                            borderRadius: '4px',
                            background: 'rgba(16, 185, 129, 0.12)',
                            color: '#10B981',
                            border: '1px solid rgba(16, 185, 129, 0.25)',
                            fontWeight: '600',
                          }}
                        >
                          ACTIVE
                        </span>
                      ) : (
                        <span
                          style={{
                            fontSize: '0.65rem',
                            padding: '3px 8px',
                            borderRadius: '4px',
                            background: 'rgba(255,255,255,0.05)',
                            color: 'rgba(255,255,255,0.5)',
                            border: '1px solid rgba(255,255,255,0.1)',
                          }}
                        >
                          UPCOMING
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="saas-card-body">
                    <p style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.5, marginBottom: '14px' }}>
                      {agent.description}
                    </p>

                    <div style={{ marginBottom: '12px' }}>
                      <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', display: 'block', marginBottom: '6px' }}>
                        Key Features:
                      </span>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                        {agent.capabilities.map((cap) => (
                          <span
                            key={cap}
                            style={{
                              fontSize: '0.7rem',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              background: 'rgba(255,255,255,0.04)',
                              border: '1px solid rgba(255,255,255,0.08)',
                              color: '#d4d4d8',
                            }}
                          >
                            {cap.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div style={{ padding: '12px 18px', borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.01)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.4)' }}>
                    {agent.isBackend ? 'Ready to assist' : 'Planned assistant'}
                  </span>

                  <button
                    className="saas-btn saas-btn-secondary"
                    onClick={() => navigate(agent.path)}
                    style={{ padding: '6px 14px', fontSize: '0.78rem' }}
                  >
                    <span>Open Assistant</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
