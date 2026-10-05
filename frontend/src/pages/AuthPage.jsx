import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, useAnimationFrame } from 'framer-motion';
import { useAuth } from '../context/AuthContext';

// Animated abstract orchestrator SVG for the left panel
function OrchestratorAbstract() {
  const [time, setTime] = useState(0);

  useAnimationFrame((t) => {
    setTime(t / 1000);
  });

  const nodes = [
    { x: 200, y: 200, r: 60, label: 'CORE', main: true },
    { x: 80, y: 100, r: 18, label: '01', delay: 0 },
    { x: 320, y: 90, r: 18, label: '02', delay: 0.4 },
    { x: 360, y: 230, r: 18, label: '03', delay: 0.8 },
    { x: 260, y: 340, r: 18, label: '04', delay: 1.2 },
    { x: 70, y: 300, r: 18, label: '05', delay: 1.6 },
  ];

  return (
    <svg className="auth-abstract-svg" viewBox="0 0 400 400" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="coreGrad" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#f5f4f0" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#f5f4f0" stopOpacity="0" />
        </radialGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Connection lines */}
      {nodes.slice(1).map((node, i) => {
        const pulse = Math.sin(time * 1.5 + node.delay) * 0.5 + 0.5;
        return (
          <line
            key={i}
            x1={nodes[0].x} y1={nodes[0].y}
            x2={node.x} y2={node.y}
            stroke="#f5f4f0"
            strokeWidth="0.75"
            strokeOpacity={0.15 + pulse * 0.2}
            strokeDasharray="4 8"
          />
        );
      })}

      {/* Core pulse ring */}
      <circle
        cx={nodes[0].x} cy={nodes[0].y}
        r={nodes[0].r + 20 + Math.sin(time) * 8}
        fill="url(#coreGrad)"
      />
      <circle
        cx={nodes[0].x} cy={nodes[0].y}
        r={nodes[0].r + 35 + Math.sin(time * 0.7) * 10}
        fill="url(#coreGrad)"
        style={{ opacity: 0.4 }}
      />

      {/* Core node */}
      <circle
        cx={nodes[0].x} cy={nodes[0].y} r={nodes[0].r}
        fill="none"
        stroke="rgba(255,255,255,0.12)"
        strokeWidth="1"
        filter="url(#glow)"
      />
      <circle
        cx={nodes[0].x} cy={nodes[0].y} r={nodes[0].r - 15}
        fill="none"
        stroke="#f5f4f0"
        strokeWidth="0.75"
        strokeOpacity="0.6"
      />
      <circle
        cx={nodes[0].x} cy={nodes[0].y} r={8}
        fill="#f5f4f0"
        fillOpacity={0.8 + Math.sin(time * 2) * 0.2}
      />

      {/* Satellite nodes */}
      {nodes.slice(1).map((node, i) => {
        const pulse = Math.sin(time + node.delay) * 0.5 + 0.5;
        const floatX = Math.sin(time * 0.8 + node.delay) * 4;
        const floatY = Math.cos(time * 0.6 + node.delay) * 4;
        return (
          <g key={i} transform={`translate(${floatX}, ${floatY})`}>
            <circle
              cx={node.x} cy={node.y} r={node.r + 4}
              fill="rgba(255,255,255,0.02)"
            />
            <circle
              cx={node.x} cy={node.y} r={node.r}
              fill="none"
              stroke="rgba(255,255,255,0.15)"
              strokeWidth="0.75"
            />
            <circle
              cx={node.x} cy={node.y} r={4}
              fill="white"
              fillOpacity={0.3 + pulse * 0.4}
            />
            <text
              x={node.x} y={node.y + 28}
              textAnchor="middle"
              fill="rgba(255,255,255,0.3)"
              fontSize="8"
              fontFamily="JetBrains Mono"
              letterSpacing="2"
            >
              {node.label}
            </text>
          </g>
        );
      })}

      {/* Grid lines */}
      {[80, 160, 240, 320].map((x) => (
        <line key={x} x1={x} y1="0" x2={x} y2="400"
          stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
      ))}
      {[80, 160, 240, 320].map((y) => (
        <line key={y} x1="0" y1={y} x2="400" y2={y}
          stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
      ))}
    </svg>
  );
}

export default function AuthPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please enter your credentials.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/authorizing');
    } catch (err) {
      setError('Authentication failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDemo = (role) => {
    const emails = {
      owner: 'marcus@axiom-corp.com',
      hr: 'sarah@axiom-corp.com',
      employee: 'jordan@axiom-corp.com',
    };
    setEmail(emails[role]);
    setPassword('demo1234');
  };

  return (
    <div className="auth-page">
      {/* Left editorial panel */}
      <div className="auth-left">
        <motion.div
          className="auth-left-content"
          initial={{ opacity: 0, x: -40 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="auth-label">AI Operating Workspace</div>

          <h1 className="auth-headline">
            <span className="auth-headline-line">INTELLIGENCE,</span>
            <span className="auth-headline-line auth-headline-indent">WITHIN YOUR</span>
            <span className="auth-headline-line auth-headline-blue">CONTROL.</span>
          </h1>

          <p className="auth-subtext">
            One workspace for every intelligent workflow.
          </p>

          <div className="auth-abstract-container">
            <OrchestratorAbstract />
          </div>

          <div className="auth-agents-preview">
            {['01 Hiring AI', '02 Research AI', '03 Knowledge AI', '04 Communication AI', '05 Insights AI'].map((a, i) => (
              <motion.span
                key={a}
                className="auth-agent-tag"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.2 + i * 0.1 }}
              >
                {a}
              </motion.span>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Right auth panel */}
      <div className="auth-right">
        <motion.div
          className="auth-panel"
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 1, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
          {/* <div className="auth-panel-logo">AXON<span className="auth-panel-logo-dot">.</span></div> */}

          <div className="auth-panel-header">
            <h2 className="auth-panel-title">Welcome back.</h2>
            <p className="auth-panel-subtitle">Sign in to your workspace.</p>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="auth-field">
              <label className="auth-field-label">Email Address</label>
              <input
                type="email"
                className="auth-input"
                placeholder="you@company.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>

            <div className="auth-field">
              <label className="auth-field-label">Password</label>
              <input
                type="password"
                className="auth-input"
                placeholder="••••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            <div className="auth-options">
              <label className="auth-checkbox">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={e => setRemember(e.target.checked)}
                />
                <span>Remember me</span>
              </label>
              <button type="button" className="auth-forgot">Forgot password?</button>
            </div>

            {error && (
              <motion.p
                className="auth-error"
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
              >
                {error}
              </motion.p>
            )}

            <motion.button
              type="submit"
              className="auth-submit"
              disabled={loading}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
            >
              {loading ? (
                <span className="auth-loading-dots">
                  <span /><span /><span />
                </span>
              ) : 'Sign In →'}
            </motion.button>

            <div className="auth-divider">
              <span>or continue with</span>
            </div>

            <button type="button" className="auth-sso-btn">
              <svg width="16" height="16" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Google SSO
            </button>
          </form>

          {/* Demo accounts */}
          <div className="auth-demo">
            <p className="auth-demo-label">Demo accounts</p>
            <div className="auth-demo-buttons">
              <button onClick={() => handleDemo('owner')} className="auth-demo-btn">Owner</button>
              <button onClick={() => handleDemo('hr')} className="auth-demo-btn">HR Admin</button>
              <button onClick={() => handleDemo('employee')} className="auth-demo-btn">Employee</button>
            </div>
          </div>

          <div className="auth-security">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <p>Your organization data remains protected by role-based access controls.</p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
