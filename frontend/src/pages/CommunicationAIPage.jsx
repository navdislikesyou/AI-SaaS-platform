import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import Navigation from '../components/Navigation';
import { useSchedule } from '../hooks/useSchedule';

const AUTOMATION_STEPS = [
  { label: 'MEETING CREATED', detail: 'Calendar event generated', done: true },
  { label: 'LINK GENERATED', detail: 'Video conference link created', done: true },
  { label: 'PARTICIPANTS NOTIFIED', detail: '4 participants received invites', done: true },
  { label: 'REMINDER SENT', detail: '30-minute advance reminder sent', done: true },
  { label: 'MEETING COMPLETED', detail: 'Duration: 48 minutes', done: false },
  { label: 'MoM GENERATED', detail: 'Minutes of meeting drafted', done: false },
];

export default function CommunicationAIPage() {
  const navigate = useNavigate();
  const [activeEvent, setActiveEvent] = useState(2);
  const [showAutomation, setShowAutomation] = useState(false);
  const [automationStep, setAutomationStep] = useState(0);
  
  const { schedule, isLoading } = useSchedule();

  const handleRunAutomation = async () => {
    setShowAutomation(true);
    for (let i = 0; i <= 5; i++) {
      await new Promise(r => setTimeout(r, 600));
      setAutomationStep(i + 1);
    }
  };

  const meeting = schedule ? schedule[activeEvent] : null;

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main">

        <div className="agent-hero communication-hero">
          <div className="agent-hero-inner">
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9 }}>
              <div className="agent-hero-breadcrumb">
                <button onClick={() => navigate('/agents')} className="breadcrumb-back">AI Agents</button>
                <span>→</span><span>Communication AI</span>
              </div>
              <div className="agent-num-label">04</div>
              <h1 className="agent-hero-heading communication">COMMUNICATION AI</h1>
              <p className="agent-hero-tagline">Turn communication<br />into automation.</p>
            </motion.div>
            <motion.div className="agent-hero-stats" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
              <div className="agent-stat"><span className="agent-stat-value">847</span><span className="agent-stat-label">Meetings Automated</span></div>
              <div className="agent-stat"><span className="agent-stat-value">100%</span><span className="agent-stat-label">Notification Rate</span></div>
              <div className="agent-stat"><span className="agent-stat-value">312</span><span className="agent-stat-label">MoMs Generated</span></div>
            </motion.div>
          </div>
        </div>

        <div className="agent-workspace">

          {/* Schedule panel */}
          <motion.div className="workspace-panel" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <div className="workspace-panel-header">
              <span className="workspace-panel-label">Today's Schedule</span>
              <span className="comm-date">Mon, Sep 7</span>
            </div>
            <div className="schedule-list">
              {isLoading ? (
                 <div style={{ padding: '20px', color: 'rgba(255,255,255,0.4)', fontSize: '13px' }}>Loading schedule...</div>
              ) : (
                (schedule || []).map((event, i) => (
                  <button
                  key={event.id}
                  className={`schedule-item ${activeEvent === i ? 'active' : ''} ${event.status}`}
                  onClick={() => setActiveEvent(i)}
                >
                  <div className="schedule-time">{event.time}</div>
                  <div className="schedule-info">
                    <span className="schedule-title">{event.title}</span>
                    <span className="schedule-meta">{event.duration} · {event.participants.length} participants</span>
                  </div>
                  {event.hasAutomation && (
                    <div className="schedule-automation-badge">AUTO</div>
                  )}
                  <div className={`schedule-status-dot ${event.status}`} />
                </button>
                ))
              )}
            </div>

            <div className="workspace-panel-header" style={{ marginTop: '32px' }}>
              <span className="workspace-panel-label">Create Meeting</span>
            </div>
            <div className="create-meeting-form">
              <input className="meeting-input" placeholder="Meeting title..." />
              <div className="meeting-fields">
                <input className="meeting-input" placeholder="Date & time" style={{ flex: 1 }} />
                <input className="meeting-input" placeholder="Duration" style={{ flex: 0, width: '100px' }} />
              </div>
              <button className="create-meeting-btn">Schedule with AI →</button>
            </div>
          </motion.div>

          {/* Meeting detail + automation */}
          <motion.div className="workspace-panel wide-panel" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <AnimatePresence mode="wait">
              {meeting && (
                <motion.div key={activeEvent} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.3 }}>
                <div className="workspace-panel-header">
                  <span className="workspace-panel-label">Meeting Details</span>
                  <span className={`meeting-status-badge ${meeting.status}`}>
                    {meeting.status === 'upcoming' ? '⬤ Upcoming' : '✓ Completed'}
                  </span>
                </div>

                <div className="meeting-detail-header">
                  <h2 className="meeting-detail-title">{meeting.title}</h2>
                  <p className="meeting-detail-meta">{meeting.time} · {meeting.duration}</p>
                </div>

                <div className="meeting-info-grid">
                  <div className="meeting-info-item">
                    <div className="workspace-field-label">Meeting Link</div>
                    <div className="meeting-link">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                      </svg>
                      meet.axiom.co/project-q4-review
                    </div>
                  </div>

                  <div className="meeting-info-item">
                    <div className="workspace-field-label">Participants</div>
                    <div className="meeting-participants">
                      {meeting.participants.map((p, i) => (
                        <span key={i} className="participant-chip">{p}</span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Automation timeline */}
                {meeting.hasAutomation && (
                  <div className="automation-section">
                    <div className="workspace-panel-header" style={{ paddingTop: '24px' }}>
                      <span className="workspace-panel-label">Automation Timeline</span>
                      {!showAutomation && (
                        <button className="run-automation-btn" onClick={handleRunAutomation}>
                          Run Automation →
                        </button>
                      )}
                    </div>

                    <div className="automation-timeline">
                      {AUTOMATION_STEPS.map((step, i) => (
                        <motion.div
                          key={i}
                          className={`automation-step ${(showAutomation ? automationStep > i : step.done) ? 'done' : ''} ${showAutomation && automationStep === i + 1 ? 'current' : ''}`}
                          initial={{ opacity: 0.4 }}
                          animate={{ opacity: (showAutomation ? automationStep > i : step.done) || (!showAutomation && !step.done) ? 1 : 0.4 }}
                        >
                          <div className="automation-step-indicator">
                            <div className="automation-dot">
                              {(showAutomation ? automationStep > i : step.done) && (
                                <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }}>✓</motion.span>
                              )}
                              {showAutomation && automationStep === i + 1 && (
                                <motion.div className="auto-scanning" animate={{ opacity: [1, 0, 1] }} transition={{ duration: 0.6, repeat: Infinity }} />
                              )}
                            </div>
                            {i < AUTOMATION_STEPS.length - 1 && <div className={`automation-line ${(showAutomation ? automationStep > i + 1 : step.done) ? 'filled' : ''}`} />}
                          </div>
                          <div className="automation-content">
                            <span className="automation-label">{step.label}</span>
                            <span className="automation-detail">{step.detail}</span>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
