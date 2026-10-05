import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import Navigation from '../components/Navigation';

function CountUp({ target, suffix = '', duration = 2000 }) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const timer = setInterval(() => {
      const elapsed = Date.now() - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.floor(eased * target));
      if (progress >= 1) clearInterval(timer);
    }, 16);
    return () => clearInterval(timer);
  }, [target, duration]);
  return <>{value.toLocaleString()}{suffix}</>;
}

const AGENT_PERFORMANCE = [
  { name: 'Hiring AI', requests: 284, color: '#FF5A00', pct: 84 },
  { name: 'Knowledge AI', requests: 612, color: '#E8FF72', pct: 100 },
  { name: 'Communication AI', requests: 193, color: '#4a9dc4', pct: 58 },
  { name: 'Research AI', requests: 147, color: '#f5f4f0', pct: 44 },
  { name: 'Insights AI', requests: 89, color: '#FFFBE8', pct: 27 },
];

const ACTIVITY_WEEKS = [
  [12, 8, 24, 16, 20, 14, 6],
  [18, 22, 15, 28, 32, 19, 11],
  [24, 30, 18, 22, 26, 20, 14],
  [28, 35, 22, 30, 42, 28, 16],
];

export default function InsightsAIPage() {
  const navigate = useNavigate();

  return (
    <div className="agent-page">
      <Navigation />
      <main className="agent-main">

        <div className="agent-hero insights-hero">
          <div className="agent-hero-inner">
            <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9 }}>
              <div className="agent-hero-breadcrumb">
                <button onClick={() => navigate('/agents')} className="breadcrumb-back">AI Agents</button>
                <span>→</span><span>Insights AI</span>
              </div>
              {/* <div className="agent-num-label">05</div> */}
              <h1 className="agent-hero-heading insights">INSIGHTS AI</h1>
              <p className="agent-hero-tagline">Understand how your<br />organization works.</p>
            </motion.div>
          </div>
        </div>

        <div className="agent-main-body insights-body">

          {/* Key metrics — editorial style */}
          <motion.div
            className="insights-metrics"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <div className="insight-metric-card">
              <div className="insight-metric-label">Total AI Requests</div>
              <div className="insight-metric-value">
                <CountUp target={1325} />
              </div>
              <div className="insight-metric-delta up">+18% this week</div>
            </div>
            <div className="insight-metric-card">
              <div className="insight-metric-label">Tasks Completed</div>
              <div className="insight-metric-value">
                <CountUp target={892} />
              </div>
              <div className="insight-metric-delta up">+24% this week</div>
            </div>
            <div className="insight-metric-card">
              <div className="insight-metric-label">Time Saved</div>
              <div className="insight-metric-value">
                <CountUp target={247} suffix="h" />
              </div>
              <div className="insight-metric-delta up">This month</div>
            </div>
            <div className="insight-metric-card">
              <div className="insight-metric-label">Most Used Agent</div>
              <div className="insight-metric-value text-metric">KNOWLEDGE</div>
              <div className="insight-metric-delta">612 requests</div>
            </div>
          </motion.div>

          {/* Two column */}
          <div className="insights-two-col">

            {/* Agent performance */}
            <motion.div
              className="workspace-panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
            >
              <div className="workspace-panel-header">
                <span className="workspace-panel-label">Agent Performance</span>
                <span className="panel-header-count">This week</span>
              </div>
              <div className="agent-perf-list">
                {AGENT_PERFORMANCE.map((agent, i) => (
                  <motion.div
                    key={agent.name}
                    className="agent-perf-item"
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 + i * 0.08 }}
                  >
                    <div className="agent-perf-header">
                      <span className="agent-perf-name">{agent.name}</span>
                      <span className="agent-perf-count">{agent.requests}</span>
                    </div>
                    <div className="agent-perf-bar-track">
                      <motion.div
                        className="agent-perf-bar"
                        initial={{ width: 0 }}
                        animate={{ width: `${agent.pct}%` }}
                        transition={{ duration: 1, delay: 0.6 + i * 0.08, ease: [0.16, 1, 0.3, 1] }}
                        style={{ background: agent.color }}
                      />
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>

            {/* Workflow activity */}
            <motion.div
              className="workspace-panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
            >
              <div className="workspace-panel-header">
                <span className="workspace-panel-label">Workflow Activity</span>
                <span className="panel-header-count">4-week view</span>
              </div>
              <div className="activity-chart">
                {ACTIVITY_WEEKS.map((week, wi) => (
                  <div key={wi} className="activity-week">
                    {week.map((val, di) => {
                      const pct = (val / 42) * 100;
                      return (
                        <motion.div
                          key={di}
                          className="activity-cell"
                          initial={{ opacity: 0, scaleY: 0 }}
                          animate={{ opacity: 1, scaleY: 1 }}
                          transition={{ delay: 0.6 + wi * 0.05 + di * 0.02 }}
                          style={{
                            background: pct > 70 ? '#E8FF72' : pct > 40 ? 'rgba(232,255,114,0.4)' : 'rgba(255,255,255,0.06)',
                            height: `${Math.max(pct * 0.8, 8)}%`,
                          }}
                          title={`${val} requests`}
                        />
                      );
                    })}
                  </div>
                ))}
              </div>
              <div className="activity-chart-labels">
                <span>4 weeks ago</span>
                <span>This week</span>
              </div>
            </motion.div>
          </div>

          {/* Recent activity log */}
          <motion.div
            className="workspace-panel"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
            style={{ margin: '0 64px 48px' }}
          >
            <div className="workspace-panel-header">
              <span className="workspace-panel-label">Recent Activity</span>
            </div>
            <div className="activity-log">
              {[
                { time: '2 min ago', agent: 'Knowledge AI', action: 'Answered: "Remote work policy details"', user: 'Jordan P.', color: '#E8FF72' },
                { time: '14 min ago', agent: 'Hiring AI', action: 'Analyzed 3 resumes for React Developer role', user: 'Sarah C.', color: '#FF5A00' },
                { time: '28 min ago', agent: 'Communication AI', action: 'Generated MoM for HR Review meeting', user: 'Marcus W.', color: '#4a9dc4' },
                { time: '1h ago', agent: 'Research AI', action: 'Summarized: BERT paper · 97% relevance', user: 'Marcus W.', color: '#f5f4f0' },
                { time: '2h ago', agent: 'Insights AI', action: 'Generated weekly performance report', user: 'Sarah C.', color: '#FFFBE8' },
              ].map((item, i) => (
                <motion.div
                  key={i}
                  className="activity-log-item"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.7 + i * 0.05 }}
                >
                  <div className="activity-log-dot" style={{ background: item.color }} />
                  <div className="activity-log-info">
                    <div className="activity-log-agent" style={{ color: item.color }}>{item.agent}</div>
                    <div className="activity-log-action">{item.action}</div>
                  </div>
                  <div className="activity-log-right">
                    <span className="activity-log-user">{item.user}</span>
                    <span className="activity-log-time">{item.time}</span>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
