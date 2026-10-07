import React, { useState } from 'react';
import {
  Zap,
  Play,
  Cpu,
  FileCheck,
  Sparkles,
  Target,
  Lightbulb,
  Compass,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-react';
import Navigation from '../components/Navigation';
import { useAgentExecution } from '../hooks/useAgentExecution';
import AgentExecutionResult from '../components/AgentExecutionResult';

const SAMPLE_PROMPTS = [
  'Draft a sprint retro action plan for the engineering leads',
  'Prepare an invitation and agenda for Friday architecture review',
  'Draft follow-up email after Q3 client presentation with next steps',
  'Propose a resource allocation plan for infrastructure migration',
];

const ACTION_PIPELINE = [
  {
    id: 'act_01',
    title: 'Sprint 24 Retro Itemization',
    type: 'draft_action',
    assignee: 'Marcus W.',
    status: 'Ready for Review',
    created: '10m ago',
  },
  {
    id: 'act_02',
    title: 'Client Demo Follow-up Package',
    type: 'propose_action',
    assignee: 'Sarah C.',
    status: 'Approved',
    created: '1h ago',
  },
  {
    id: 'act_03',
    title: 'Q4 Budget Sync Schedule Draft',
    type: 'draft_action',
    assignee: 'Jordan P.',
    status: 'Dispatched',
    created: '3h ago',
  },
];

export default function AutomationAIPage() {
  const [activeTab, setActiveTab] = useState('studio');
  const [prompt, setPrompt] = useState('');

  const { execute, isLoading, response, error, executionMeta } = useAgentExecution();

  const handleExecute = async (customPrompt = null) => {
    const text = customPrompt || prompt;
    if (!text.trim() || isLoading) return;
    setPrompt(text);

    // The adapter requires `instruction`, not `prompt`.
    // draft_action is the only implemented operation.
    await execute('automation', 'draft_action', { instruction: text });
  };

  // Unwrap the execute envelope. useAgentExecution stores the full body:
  //   response           -> { success, data: A, message, request_id }
  //   response.data      -> A  = { agent, operation, data: B, duration_ms, ... }
  //   response.data.data -> B  = { meeting, recipients, email }
  // Guarded on the operation, and never defaulted, so absent data renders as
  // nothing rather than as invented meeting details.
  const automationOp = response?.data;
  const draft =
    automationOp?.operation === 'draft_action'
      ? automationOp.data
      : null;

  const meeting = draft?.meeting;
  const recipients = Array.isArray(draft?.recipients)
    ? draft.recipients
    : [];
  const emailBody = draft?.email || '';

  return (
    <div className="saas-workbench">
      <Navigation />

      <main className="saas-main-container">
        {/* Topbar */}
        <div className="saas-topbar">
          <div className="saas-breadcrumb">
            <span className="saas-breadcrumb-item">Agents</span>
            <span className="saas-breadcrumb-sep">/</span>
            <span className="saas-breadcrumb-active">Automation AI</span>
          </div>

          <div className="saas-topbar-actions">
            <span
              style={{
                fontFamily: 'JetBrains Mono',
                fontSize: '0.68rem',
                padding: '3px 8px',
                borderRadius: '4px',
                background: 'rgba(74,157,196,0.1)',
                color: '#4A9DC4',
                border: '1px solid rgba(74,157,196,0.25)',
              }}
            >
              adapter: automation.py
            </span>
          </div>
        </div>

        {/* Page Body */}
        <div className="saas-page-body">
          {/* Header */}
          <div className="saas-page-header">
            <div className="saas-page-title-wrap">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Zap size={22} color="#4A9DC4" />
                <h1 className="saas-page-title">Task Automation Assistant</h1>
              </div>
              <p className="saas-page-subtitle">
                Turn simple requests into drafted emails, meeting summaries, and task plans with 1-click human review.
              </p>
            </div>
          </div>

          {/* Workbench Tabs */}
          <div className="saas-tabs-bar">
            <button
              className={`saas-tab-btn ${activeTab === 'studio' ? 'active' : ''}`}
              onClick={() => setActiveTab('studio')}
            >
              <Sparkles size={15} />
              <span>Create Draft</span>
            </button>
            <button
              className={`saas-tab-btn ${activeTab === 'pipeline' ? 'active' : ''}`}
              onClick={() => setActiveTab('pipeline')}
            >
              <FileCheck size={15} />
              <span>Review Queue ({ACTION_PIPELINE.length})</span>
            </button>
            <button
              className={`saas-tab-btn ${activeTab === 'seam' ? 'active' : ''}`}
              onClick={() => setActiveTab('seam')}
            >
              <Cpu size={15} />
              <span>Assistant Info</span>
            </button>
          </div>

          {/* TAB 1: Studio */}
          {activeTab === 'studio' && (
            <div className="saas-workbench-grid">
              <div>
                <div className="saas-card" style={{ marginBottom: '20px' }}>
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Zap size={16} color="#4A9DC4" />
                      <span>What would you like to draft?</span>
                    </div>

                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '3px 10px',
                          borderRadius: '4px',
                          background: '#4A9DC4',
                          color: '#000',
                          border: '1px solid rgba(255,255,255,0.1)',
                        }}
                      >
                        Draft Action
                      </span>
                      <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)' }}>
                        Drafting only — nothing is sent or scheduled.
                      </span>
                    </div>
                  </div>

                  <div className="saas-card-body">
                    <div className="saas-input-group">
                      <label className="saas-label">Describe your request in natural language</label>
                      <textarea
                        className="saas-textarea"
                        placeholder="e.g. Draft a sprint retro action plan and follow-up email for the engineering leads..."
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {SAMPLE_PROMPTS.map((sp, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => handleExecute(sp)}
                            style={{
                              background: 'rgba(255,255,255,0.04)',
                              border: '1px solid rgba(255,255,255,0.08)',
                              borderRadius: '4px',
                              padding: '4px 8px',
                              fontSize: '0.72rem',
                              color: 'rgba(255,255,255,0.7)',
                              cursor: 'pointer',
                            }}
                          >
                            {sp}
                          </button>
                        ))}
                      </div>

                      <button
                        className="saas-btn"
                        onClick={() => handleExecute()}
                        disabled={!prompt.trim() || isLoading}
                        style={{ background: '#4A9DC4', color: '#000', fontWeight: 600, flexShrink: 0, marginLeft: '12px' }}
                      >
                        <Play size={14} fill="#000" />
                        <span>{isLoading ? 'Drafting...' : 'Generate Draft'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Live Backend Execution Result Card */}
                <AgentExecutionResult
                  executionMeta={executionMeta}
                  isLoading={isLoading}
                  error={error}
                  response={response}
                  agentColor="#4A9DC4"
                  simulatedData={
                    draft ? (
                      <div style={{ marginTop: '12px' }}>
                        {meeting && (
                          <div
                            style={{
                              background: 'rgba(255,255,255,0.03)',
                              padding: '16px',
                              borderRadius: '6px',
                              border: '1px solid rgba(255,255,255,0.08)',
                              marginBottom: '16px',
                            }}
                          >
                            <div
                              style={{
                                fontWeight: 600,
                                color: '#f4f4f5',
                                marginBottom: '10px',
                                fontSize: '0.9rem',
                              }}
                            >
                              {meeting.title}
                            </div>
                            <div
                              style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                                gap: '10px',
                                fontSize: '0.8rem',
                              }}
                            >
                              <div>
                                <div
                                  style={{
                                    fontSize: '0.65rem',
                                    color: 'rgba(255,255,255,0.45)',
                                    fontFamily: 'JetBrains Mono',
                                  }}
                                >
                                  DATE
                                </div>
                                <div style={{ color: '#f4f4f5' }}>{meeting.date}</div>
                              </div>
                              <div>
                                <div
                                  style={{
                                    fontSize: '0.65rem',
                                    color: 'rgba(255,255,255,0.45)',
                                    fontFamily: 'JetBrains Mono',
                                  }}
                                >
                                  TIME
                                </div>
                                <div style={{ color: '#f4f4f5' }}>{meeting.time}</div>
                              </div>
                              <div>
                                <div
                                  style={{
                                    fontSize: '0.65rem',
                                    color: 'rgba(255,255,255,0.45)',
                                    fontFamily: 'JetBrains Mono',
                                  }}
                                >
                                  VENUE
                                </div>
                                <div style={{ color: '#f4f4f5' }}>{meeting.venue}</div>
                              </div>
                              <div>
                                <div
                                  style={{
                                    fontSize: '0.65rem',
                                    color: 'rgba(255,255,255,0.45)',
                                    fontFamily: 'JetBrains Mono',
                                  }}
                                >
                                  ATTENDEES
                                </div>
                                <div style={{ color: '#f4f4f5' }}>
                                  {meeting.attendees?.length
                                    ? meeting.attendees.join(', ')
                                    : 'None'}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {recipients.length > 0 && (
                          <>
                            <div
                              style={{
                                fontSize: '0.7rem',
                                color: 'rgba(255,255,255,0.5)',
                                fontFamily: 'JetBrains Mono',
                                textTransform: 'uppercase',
                                marginBottom: '8px',
                              }}
                            >
                              RESOLVED RECIPIENTS:
                            </div>
                            <div
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '6px',
                                marginBottom: '16px',
                              }}
                            >
                              {recipients.map((person) => (
                                <div
                                  key={person.email}
                                  style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    gap: '12px',
                                    padding: '8px 12px',
                                    background: 'rgba(255,255,255,0.02)',
                                    border: '1px solid rgba(255,255,255,0.06)',
                                    borderRadius: '4px',
                                    fontSize: '0.75rem',
                                  }}
                                >
                                  <span style={{ color: '#f4f4f5' }}>{person.name}</span>
                                  <span
                                    style={{
                                      color: '#4A9DC4',
                                      fontFamily: 'JetBrains Mono',
                                      wordBreak: 'break-all',
                                      textAlign: 'right',
                                    }}
                                  >
                                    {person.email}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </>
                        )}

                        {emailBody && (
                          <>
                            <div
                              style={{
                                fontSize: '0.7rem',
                                color: 'rgba(255,255,255,0.5)',
                                fontFamily: 'JetBrains Mono',
                                textTransform: 'uppercase',
                                marginBottom: '8px',
                              }}
                            >
                              DRAFTED EMAIL (NOT SENT):
                            </div>
                            <div
                              style={{
                                background: 'rgba(255,255,255,0.03)',
                                padding: '16px',
                                borderRadius: '6px',
                                border: '1px solid rgba(255,255,255,0.08)',
                                fontSize: '0.85rem',
                                lineHeight: 1.6,
                                color: '#f4f4f5',
                                whiteSpace: 'pre-wrap',
                                fontFamily: 'inherit',
                              }}
                            >
                              {emailBody}
                            </div>
                          </>
                        )}
                      </div>
                    ) : null
                  }
                />
              </div>

              {/* Right Column: Seam Specs */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Cpu size={16} color="#4A9DC4" />
                      <span>Adapter Specification</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Adapter Class:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>AutomationAgentAdapter</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Timeout Limit:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>180.0 seconds</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Side Effects:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#E8FF72' }}>None (Draft Only)</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Execution Seam:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#4A9DC4' }}>run(operation, payload)</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Action Pipeline */}
          {activeTab === 'pipeline' && (
            <div className="saas-card">
              <div className="saas-card-header">
                <div className="saas-card-title">
                  <FileCheck size={16} color="#4A9DC4" />
                  <span>Draft Action Queue</span>
                </div>
              </div>

              <table className="saas-table">
                <thead>
                  <tr>
                    <th>Action Proposal</th>
                    <th>Operation</th>
                    <th>Requester</th>
                    <th>State</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {ACTION_PIPELINE.map((act) => (
                    <tr key={act.id}>
                      <td style={{ fontWeight: 500, color: '#fafafa' }}>{act.title}</td>
                      <td>
                        <span style={{ fontFamily: 'JetBrains Mono', fontSize: '0.7rem', color: '#4A9DC4' }}>
                          {act.type}
                        </span>
                      </td>
                      <td>{act.assignee}</td>
                      <td>
                        <span
                          style={{
                            fontFamily: 'JetBrains Mono',
                            fontSize: '0.65rem',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: 'rgba(74,157,196,0.1)',
                            color: '#4A9DC4',
                            border: '1px solid rgba(74,157,196,0.25)',
                          }}
                        >
                          {act.status}
                        </span>
                      </td>
                      <td style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem' }}>{act.created}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: What This Assistant Does (User Guide) */}
          {activeTab === 'seam' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Overview Card */}
              <div className="saas-card">
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <Zap size={18} color="#4A9DC4" />
                    <span>What the Task Automation Assistant Does</span>
                  </div>
                </div>
                <div className="saas-card-body" style={{ lineHeight: 1.7, fontSize: '0.88rem', color: 'rgba(255,255,255,0.85)' }}>
                  <p style={{ marginBottom: '14px' }}>
                    The <strong>Task Automation Assistant</strong> turns conversational prompts, rough notes, and quick thoughts into structured, ready-to-use business deliverables. Whether you need a team meeting agenda, a follow-up client email, or a sprint task checklist, this assistant formats and organizes everything cleanly.
                  </p>
                  <p>
                    <strong>Human-in-the-Loop Safety:</strong> This assistant never triggers external actions or sends messages on its own. Every draft, email, or proposed plan is placed into your review queue for you to inspect, edit, and approve.
                  </p>
                </div>
              </div>

              {/* 4 Core Capabilities Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Target size={16} color="#4A9DC4" />
                      <span>1. Professional Email & Communication Drafts</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Draft follow-up emails, leadership announcements, and client check-ins with proper subject lines, bulleted summaries, and clear next steps.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <CheckCircle2 size={16} color="#4A9DC4" />
                      <span>2. Structured Meeting Agendas</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Transform rough discussion topics into polished agendas with estimated time allocations, discussion goals, and attendee assignments.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Lightbulb size={16} color="#4A9DC4" />
                      <span>3. Sprint & Task Action Plans</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Turn retro notes or project requirements into itemized action items with assignees, priorities, and clear definition of done.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <FileCheck size={16} color="#4A9DC4" />
                      <span>4. Review Queue Management</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Keeps track of all drafted actions in a centralized pipeline where managers and team leads can review, revise, and sign off.
                  </div>
                </div>
              </div>

              {/* How to use */}
              <div className="saas-card">
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <Compass size={16} color="#E8FF72" />
                    <span>How to Use This Assistant</span>
                  </div>
                </div>
                <div className="saas-card-body" style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.75)', lineHeight: 1.7 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(74,157,196,0.15)', color: '#4A9DC4', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        1
                      </span>
                      <span>Go to the <strong>Create Draft</strong> tab and choose the action type (e.g. <em>Draft Email / Note</em> or <em>Propose Task Plan</em>).</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(74,157,196,0.15)', color: '#4A9DC4', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        2
                      </span>
                      <span>Describe your request in natural language or pick one of the sample prompt chips.</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(74,157,196,0.15)', color: '#4A9DC4', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        3
                      </span>
                      <span>Click <strong>Generate Draft</strong> to receive a formatted, ready-to-use document. Check the <strong>Review Queue</strong> anytime to manage pending items.</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Safety Guarantee */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '14px 20px',
                  borderRadius: '10px',
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.2)',
                  fontSize: '0.82rem',
                  color: 'rgba(255,255,255,0.85)',
                }}
              >
                <ShieldCheck size={20} color="#10B981" />
                <span><strong>Zero Unintended Side Effects:</strong> The assistant drafts proposals for you to review. It will never send an email or change a calendar event without your confirmation.</span>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
