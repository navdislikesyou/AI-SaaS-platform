import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  Cpu,
  BookOpen,
  Zap,
  BarChart3,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  Search,
  FileText,
  Clock,
  Send,
} from 'lucide-react';
import PageTransition from '../components/PageTransition';
import { useSystemHealth } from '../hooks/useSystemHealth';

export default function LandingPage() {
  const navigate = useNavigate();
  const { isOnline, latency, refresh } = useSystemHealth();
  const [activeTab, setActiveTab] = useState('knowledge');

  const assistants = [
    {
      id: 'knowledge',
      name: 'Knowledge Assistant',
      role: 'Company Q&A & Document Search',
      badge: 'DOCUMENTS & POLICIES',
      color: '#E8FF72',
      route: '/agents/knowledge',
      tagline: 'Instant, cited answers from your internal documents',
      description: 'Search across employee handbooks, engineering guidelines, company policies, and FAQs with direct source references.',
      samplePrompt: 'What is our standard vacation and leave policy for remote employees?',
      sampleAnswer:
        'Full-time remote employees receive 20 days of paid vacation and 10 wellness days annually. Time off requests can be submitted via the HR Portal with at least 5 business days advance notice.',
      sourceDoc: 'Employee Handbook 2026 • Section 4.2',
    },
    {
      id: 'automation',
      name: 'Task Automation',
      role: 'Drafts, Agendas & Workflows',
      badge: 'WORKFLOWS & TASKS',
      color: '#4A9DC4',
      route: '/agents/automation',
      tagline: 'Turn simple requests into ready-to-review drafts',
      description: 'Draft meeting agendas, follow-up emails, sprint action items, and team announcements with built-in human approval.',
      samplePrompt: 'Draft an email recap and action plan for Friday\'s product architecture review.',
      sampleAnswer:
        'Subject: Recap & Action Items — Architecture Review (Oct 5)\n\nKey Decisions:\n1. Transitioning to dedicated adapter runtime for all AI assistants.\n2. Action Item: Sarah to finalize schema validation by Wednesday.\n3. Next Sync: Friday 10:00 AM EST.',
      sourceDoc: 'Generated Draft • Awaiting Review',
    },
    {
      id: 'performance',
      name: 'Performance Insights',
      role: 'Team Metrics & Data Trends',
      badge: 'BUSINESS ANALYTICS',
      color: '#FF5A00',
      route: '/agents/performance',
      tagline: 'Simple, visual analytics without complex spreadsheets',
      description: 'Track team velocity, goal completion rates, customer retention, and department KPIs with clear visual summaries.',
      samplePrompt: 'Show our quarterly goal completion rate and compare it to last quarter.',
      sampleAnswer:
        'Q3 Goal Completion Rate: 91.4% (+6.8% compared to Q2).\nTop Performing Category: Customer Success (96% SLA compliance).\nActive Initiatives: 14 Completed, 2 In Progress, 0 Blocked.',
      sourceDoc: 'Q3 Executive Performance Report',
    },
  ];

  const currentAssistant = assistants.find((a) => a.id === activeTab) || assistants[0];

  return (
    <PageTransition>
      <div style={{ minHeight: '100vh', background: '#090a0f', color: '#f4f4f5' }}>
        {/* Navigation Bar */}
        <header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '18px 48px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            background: 'rgba(9, 10, 15, 0.85)',
            backdropFilter: 'blur(16px)',
            position: 'sticky',
            top: 0,
            zIndex: 100,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                cursor: 'pointer',
              }}
              onClick={() => navigate('/')}
            >
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #E8FF72, #4A9DC4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#000',
                  fontWeight: '800',
                  fontSize: '14px',
                  fontFamily: 'Syne, sans-serif',
                }}
              >
                A
              </div>
              <span
                style={{
                  fontSize: '1.15rem',
                  fontWeight: '700',
                  letterSpacing: '0.03em',
                  fontFamily: 'Syne, sans-serif',
                }}
              >
                AXON
              </span>
            </div>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '3px 10px',
                borderRadius: '12px',
                background: 'rgba(255, 255, 255, 0.06)',
                color: 'rgba(255, 255, 255, 0.65)',
              }}
            >
              AI Workspace
            </span>
          </div>

          <nav style={{ display: 'flex', alignItems: 'center', gap: '32px' }}>
            <span
              onClick={() => navigate('/orchestrator')}
              style={{ fontSize: '0.88rem', color: 'rgba(255, 255, 255, 0.7)', cursor: 'pointer' }}
              onMouseEnter={(e) => (e.target.style.color = '#fff')}
              onMouseLeave={(e) => (e.target.style.color = 'rgba(255, 255, 255, 0.7)')}
            >
              Command Center
            </span>
            <span
              onClick={() => navigate('/agents')}
              style={{ fontSize: '0.88rem', color: 'rgba(255, 255, 255, 0.7)', cursor: 'pointer' }}
              onMouseEnter={(e) => (e.target.style.color = '#fff')}
              onMouseLeave={(e) => (e.target.style.color = 'rgba(255, 255, 255, 0.7)')}
            >
              AI Assistants
            </span>
            <span
              onClick={() => navigate('/settings')}
              style={{ fontSize: '0.88rem', color: 'rgba(255, 255, 255, 0.7)', cursor: 'pointer' }}
              onMouseEnter={(e) => (e.target.style.color = '#fff')}
              onMouseLeave={(e) => (e.target.style.color = 'rgba(255, 255, 255, 0.7)')}
            >
              Settings
            </span>
          </nav>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div
              onClick={refresh}
              title="Click to check connection"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '5px 12px',
                borderRadius: '20px',
                background: isOnline ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                border: `1px solid ${isOnline ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
                cursor: 'pointer',
                fontSize: '0.78rem',
                color: isOnline ? '#10B981' : '#EF4444',
              }}
            >
              <span
                style={{
                  width: '7px',
                  height: '7px',
                  borderRadius: '50%',
                  background: isOnline ? '#10B981' : '#EF4444',
                }}
              />
              <span>{isOnline ? 'Systems Operational' : 'Reconnecting...'}</span>
            </div>

            <button
              onClick={() => navigate('/orchestrator')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '9px 18px',
                borderRadius: '8px',
                background: '#E8FF72',
                color: '#000',
                fontWeight: '600',
                fontSize: '0.88rem',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <span>Open Workspace</span>
              <ArrowRight size={15} />
            </button>
          </div>
        </header>

        {/* Hero Section */}
        <section
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '72px 24px 48px',
            textAlign: 'center',
          }}
        >
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 16px',
              borderRadius: '20px',
              background: 'rgba(232, 255, 114, 0.08)',
              border: '1px solid rgba(232, 255, 114, 0.2)',
              color: '#E8FF72',
              fontSize: '0.82rem',
              fontWeight: '500',
              marginBottom: '28px',
            }}
          >
            <Sparkles size={14} />
            <span>AI-POWERED WORKSPACE FOR TEAMS</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            style={{
              fontSize: 'clamp(2.5rem, 5vw, 4.2rem)',
              fontWeight: '800',
              lineHeight: 1.1,
              letterSpacing: '-0.03em',
              fontFamily: 'Syne, sans-serif',
              maxWidth: '920px',
              margin: '0 auto 20px',
            }}
          >
            Your Organization’s All-in-One AI Workforce
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            style={{
              fontSize: '1.15rem',
              lineHeight: 1.6,
              color: 'rgba(255, 255, 255, 0.65)',
              maxWidth: '680px',
              margin: '0 auto 36px',
            }}
          >
            Empower your team with specialized AI assistants that understand company documents, draft communications, and track performance goals — all in one simple, secure workspace.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            style={{ display: 'flex', alignItems: 'center', gap: '16px', justifyContent: 'center', flexWrap: 'wrap' }}
          >
            <button
              onClick={() => navigate('/orchestrator')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '14px 28px',
                borderRadius: '8px',
                background: '#E8FF72',
                color: '#000',
                fontWeight: '700',
                fontSize: '0.95rem',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <span>Get Started</span>
              <ArrowRight size={18} />
            </button>

            <button
              onClick={() => navigate('/agents')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '14px 24px',
                borderRadius: '8px',
                background: 'rgba(255, 255, 255, 0.05)',
                color: '#fff',
                fontWeight: '600',
                fontSize: '0.95rem',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                cursor: 'pointer',
              }}
            >
              <Cpu size={18} />
              <span>Explore AI Assistants</span>
            </button>
          </motion.div>

          {/* User Benefits Bar */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '28px',
              marginTop: '44px',
              padding: '14px 24px',
              borderRadius: '12px',
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid rgba(255, 255, 255, 0.06)',
              fontSize: '0.85rem',
              color: 'rgba(255, 255, 255, 0.65)',
              flexWrap: 'wrap',
              justifyContent: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={16} color="#10B981" />
              <span>Instant Answers from Docs</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={16} color="#10B981" />
              <span>Human Approval Before Action</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={16} color="#10B981" />
              <span>Enterprise Data Privacy</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={16} color="#10B981" />
              <span>Fast, Reliable Workspace</span>
            </div>
          </div>
        </section>

        {/* Live Interactive Assistant Demo */}
        <section
          style={{
            maxWidth: '1100px',
            margin: '0 auto',
            padding: '16px 24px 80px',
          }}
        >
          <div
            style={{
              background: '#0e1118',
              borderRadius: '16px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              overflow: 'hidden',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)',
            }}
          >
            {/* Assistant Tabs */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 24px',
                background: '#131822',
                borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: '600', color: 'rgba(255, 255, 255, 0.8)' }}>
                  Interactive Assistant Preview
                </span>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                {assistants.map((assistant) => (
                  <button
                    key={assistant.id}
                    onClick={() => setActiveTab(assistant.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '7px 14px',
                      borderRadius: '6px',
                      border: '1px solid',
                      borderColor: activeTab === assistant.id ? assistant.color : 'rgba(255, 255, 255, 0.08)',
                      background: activeTab === assistant.id ? 'rgba(255, 255, 255, 0.06)' : 'transparent',
                      color: activeTab === assistant.id ? '#fff' : 'rgba(255, 255, 255, 0.55)',
                      fontSize: '0.82rem',
                      fontWeight: activeTab === assistant.id ? '600' : '400',
                      cursor: 'pointer',
                    }}
                  >
                    <span
                      style={{
                        width: '7px',
                        height: '7px',
                        borderRadius: '50%',
                        background: assistant.color,
                      }}
                    />
                    <span>{assistant.name}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Interactive Preview Content */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr', minHeight: '360px' }}>
              {/* Left Column: Assistant Info */}
              <div style={{ padding: '36px', borderRight: '1px solid rgba(255, 255, 255, 0.08)' }}>
                <span
                  style={{
                    fontSize: '0.72rem',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    background: 'rgba(255, 255, 255, 0.08)',
                    color: currentAssistant.color,
                    fontWeight: '600',
                    display: 'inline-block',
                    marginBottom: '14px',
                  }}
                >
                  {currentAssistant.badge}
                </span>

                <h3 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '10px' }}>
                  {currentAssistant.name}
                </h3>
                <p style={{ color: 'rgba(255, 255, 255, 0.65)', lineHeight: 1.6, fontSize: '0.92rem', marginBottom: '28px' }}>
                  {currentAssistant.description}
                </p>

                <button
                  onClick={() => navigate(currentAssistant.route)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '11px 22px',
                    borderRadius: '8px',
                    background: currentAssistant.color,
                    color: '#000',
                    fontWeight: '700',
                    fontSize: '0.88rem',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  <span>Open {currentAssistant.name}</span>
                  <ArrowRight size={16} />
                </button>
              </div>

              {/* Right Column: Natural Language Preview */}
              <div style={{ background: '#0a0d14', padding: '32px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {/* User Prompt Bubble */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.45)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    User Request
                  </div>
                  <div
                    style={{
                      background: 'rgba(255, 255, 255, 0.04)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '8px',
                      padding: '14px 16px',
                      fontSize: '0.9rem',
                      color: '#f4f4f5',
                    }}
                  >
                    "{currentAssistant.samplePrompt}"
                  </div>
                </div>

                {/* Assistant Output Bubble */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.75rem', color: currentAssistant.color, fontWeight: '600' }}>
                      {currentAssistant.name} Response
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'rgba(255, 255, 255, 0.4)' }}>
                      {currentAssistant.sourceDoc}
                    </span>
                  </div>
                  <div
                    style={{
                      background: '#07090e',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '8px',
                      padding: '16px',
                      fontSize: '0.88rem',
                      lineHeight: 1.6,
                      color: '#e2e8f0',
                      whiteSpace: 'pre-line',
                    }}
                  >
                    {currentAssistant.sampleAnswer}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 3 Core Benefits */}
        <section
          style={{
            maxWidth: '1100px',
            margin: '0 auto',
            padding: '0 24px 96px',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: '44px' }}>
            <h2 style={{ fontSize: '2rem', fontWeight: '700', fontFamily: 'Syne, sans-serif' }}>
              Why Teams Love This Platform
            </h2>
            <p style={{ color: 'rgba(255, 255, 255, 0.6)', marginTop: '8px' }}>
              Built to simplify workflows without requiring technical expertise.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px' }}>
            <div
              style={{
                padding: '28px',
                borderRadius: '12px',
                background: '#0d1017',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '10px',
                  background: 'rgba(232, 255, 114, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#E8FF72',
                  marginBottom: '18px',
                }}
              >
                <Search size={20} />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: '600', marginBottom: '8px' }}>
                Instant Internal Answers
              </h3>
              <p style={{ color: 'rgba(255, 255, 255, 0.6)', lineHeight: 1.6, fontSize: '0.88rem' }}>
                No more digging through folders. Get exact answers with citations to the original employee guides and policy documents.
              </p>
            </div>

            <div
              style={{
                padding: '28px',
                borderRadius: '12px',
                background: '#0d1017',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '10px',
                  background: 'rgba(74, 157, 196, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#4A9DC4',
                  marginBottom: '18px',
                }}
              >
                <Zap size={20} />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: '600', marginBottom: '8px' }}>
                Draft in Seconds
              </h3>
              <p style={{ color: 'rgba(255, 255, 255, 0.6)', lineHeight: 1.6, fontSize: '0.88rem' }}>
                Turn messy thoughts into polished communications and task plans. You always have the final say before anything is approved.
              </p>
            </div>

            <div
              style={{
                padding: '28px',
                borderRadius: '12px',
                background: '#0d1017',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '10px',
                  background: 'rgba(255, 90, 0, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#FF5A00',
                  marginBottom: '18px',
                }}
              >
                <BarChart3 size={20} />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: '600', marginBottom: '8px' }}>
                Clear Progress Insights
              </h3>
              <p style={{ color: 'rgba(255, 255, 255, 0.6)', lineHeight: 1.6, fontSize: '0.88rem' }}>
                Track milestone progress, sprint efficiency, and quarterly achievements without complex data configuration.
              </p>
            </div>
          </div>
        </section>

        {/* Footer */}
        <footer
          style={{
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            background: '#07090e',
            padding: '36px 48px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.85rem',
            color: 'rgba(255, 255, 255, 0.5)',
          }}
        >
          <div>© 2026 AXON Workspace. All rights reserved.</div>
          <div style={{ display: 'flex', gap: '24px' }}>
            <span onClick={() => navigate('/orchestrator')} style={{ cursor: 'pointer' }}>
              Command Center
            </span>
            <span onClick={() => navigate('/agents')} style={{ cursor: 'pointer' }}>
              AI Assistants
            </span>
            <span onClick={() => navigate('/settings')} style={{ cursor: 'pointer' }}>
              Settings
            </span>
          </div>
        </footer>
      </div>
    </PageTransition>
  );
}
