import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, AlertCircle } from 'lucide-react';
import Navigation from '../components/Navigation';
import { useActivity } from '../hooks/useActivity';

const AGENT_COLORS = {
  knowledge: '#E8FF72',
  automation: '#4a9dc4',
  performance: '#FF5A00',
};

const AGENT_LABELS = {
  knowledge: 'Knowledge',
  automation: 'Automation',
  performance: 'Performance',
};

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

function formatDay(iso) {
  try {
    const date = new Date(iso);
    const today = new Date();

    const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

    const days = Math.round((startOfDay(today) - startOfDay(date)) / 86400000);

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';

    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

function groupByDay(records) {
  const groups = [];

  records.forEach((record) => {
    const label = formatDay(record.timestamp);
    const last = groups[groups.length - 1];

    if (last && last.label === label) {
      last.items.push(record);
    } else {
      groups.push({ label, items: [record] });
    }
  });

  return groups;
}

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

  const { activities, isLoading: activityLoading } = useActivity();
  const groupedActivity = groupByDay(activities);

  return (
    <div className="saas-workbench">
      <Navigation />
      <main className="saas-main-container">

        <div className="saas-topbar">
          <div className="saas-breadcrumb">
            <span className="saas-breadcrumb-item">Organization</span>
            <span className="saas-breadcrumb-sep">/</span>
            <span className="saas-breadcrumb-active">Activity History</span>
          </div>
        </div>

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
              {activityLoading && (
                <div className="activity-log-item">
                  <div className="activity-log-dot" style={{ background: 'rgba(255,255,255,0.2)' }} />
                  <div className="activity-log-info">
                    <div className="activity-log-action">Loading activity…</div>
                  </div>
                </div>
              )}

              {!activityLoading && groupedActivity.length === 0 && (
                <div className="activity-log-item">
                  <div className="activity-log-dot" style={{ background: 'rgba(255,255,255,0.2)' }} />
                  <div className="activity-log-info">
                    <div className="activity-log-action">No activity yet.</div>
                  </div>
                </div>
              )}

              {groupedActivity.map((group) => (
                <div key={group.label}>
                  <div className="activity-log-user" style={{ padding: '10px 0 4px' }}>
                    {group.label}
                  </div>

                  {group.items.map((item, i) => {
                    const color = AGENT_COLORS[item.agent] || '#f5f4f0';
                    const failed = item.status === 'failed';

                    return (
                      <motion.div
                        key={item.id}
                        className="activity-log-item"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.7 + i * 0.05 }}
                      >
                        <div className="activity-log-dot" style={{ background: color }} />
                        <div className="activity-log-info">
                          <div className="activity-log-agent" style={{ color }}>
                            {AGENT_LABELS[item.agent] || item.agent}
                          </div>
                          <div className="activity-log-action">{item.description}</div>
                          <div className="activity-log-user" style={{ marginTop: '2px' }}>
                            {failed ? (
                              <span style={{ color: '#F87171', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                <AlertCircle size={11} />
                                Failed
                              </span>
                            ) : (
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                <CheckCircle2 size={11} />
                                Completed
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="activity-log-right">
                          <span className="activity-log-time">{formatTime(item.timestamp)}</span>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
