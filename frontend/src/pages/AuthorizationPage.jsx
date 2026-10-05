import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../context/AuthContext';

const AUTH_STEPS = [
  { id: 'identity', label: 'IDENTITY VERIFIED', detail: 'Cryptographic token validated' },
  { id: 'role', label: 'ROLE VERIFIED', detail: 'Organizational role confirmed' },
  { id: 'permissions', label: 'PERMISSIONS CHECKED', detail: 'Module access evaluated' },
  { id: 'organization', label: 'ORGANIZATION VERIFIED', detail: 'Workspace isolated and ready' },
  { id: 'ready', label: 'AI WORKSPACE READY', detail: 'Initializing orchestrator', final: true },
];

function StepLine({ step, isActive, isComplete, index }) {
  return (
    <motion.div
      className={`auth-step ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''} ${step.final ? 'final' : ''}`}
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: isActive || isComplete ? 1 : 0.15, x: 0 }}
      transition={{ duration: 0.5, delay: index * 0.05 }}
    >
      <div className="auth-step-connector">
        <div className="auth-step-dot">
          {isComplete && !step.final && (
            <motion.div
              className="auth-step-check"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.3, type: 'spring' }}
            />
          )}
          {step.final && isComplete && (
            <motion.div
              className="auth-step-check final"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.3, type: 'spring' }}
            />
          )}
          {isActive && !isComplete && (
            <motion.div
              className="auth-step-scanning"
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 0.8, repeat: Infinity }}
            />
          )}
        </div>
        {index < AUTH_STEPS.length - 1 && (
          <div className="auth-step-line">
            {isComplete && (
              <motion.div
                className="auth-step-line-fill"
                initial={{ scaleY: 0 }}
                animate={{ scaleY: 1 }}
                transition={{ duration: 0.4 }}
              />
            )}
          </div>
        )}
      </div>

      <div className="auth-step-content">
        <div className="auth-step-label">{step.label}</div>
        {(isActive || isComplete) && (
          <motion.div
            className="auth-step-detail"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            transition={{ duration: 0.3 }}
          >
            {step.detail}
          </motion.div>
        )}
      </div>

      <div className="auth-step-status">
        {isComplete && !step.final && <span className="status-ok">OK</span>}
        {step.final && isComplete && <span className="status-ready">READY</span>}
        {isActive && !isComplete && <span className="status-checking">...</span>}
      </div>
    </motion.div>
  );
}

export default function AuthorizationPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!user) {
      navigate('/login');
      return;
    }

    const runSteps = async () => {
      for (let i = 0; i < AUTH_STEPS.length; i++) {
        setCurrentStep(i);
        await new Promise(r => setTimeout(r, 900));
        setCompletedSteps(prev => [...prev, i]);
        if (i < AUTH_STEPS.length - 1) {
          await new Promise(r => setTimeout(r, 200));
        }
      }
      await new Promise(r => setTimeout(r, 800));
      setDone(true);
      await new Promise(r => setTimeout(r, 600));
      navigate('/orchestrator');
    };

    const timer = setTimeout(runSteps, 400);
    return () => clearTimeout(timer);
  }, [user, navigate]);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  return (
    <div className="authz-page">
      {/* Background grid */}
      <div className="authz-bg-grid" />

      <div className="authz-content">
        {/* Top identity info */}
        <motion.div
          className="authz-identity"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <div className="authz-greeting">{greeting}, {user?.name?.split(' ')[0]}</div>
          <div className="authz-meta">
            <span className="authz-meta-item">
              <span className="authz-meta-key">Role</span>
              <span className="authz-meta-value">{user?.role}</span>
            </span>
            <span className="authz-meta-sep">·</span>
            <span className="authz-meta-item">
              <span className="authz-meta-key">Access</span>
              <span className="authz-meta-value">{user?.accessLevel}</span>
            </span>
            <span className="authz-meta-sep">·</span>
            <span className="authz-meta-item">
              <span className="authz-meta-key">Organization</span>
              <span className="authz-meta-value">{user?.organization}</span>
            </span>
          </div>
        </motion.div>

        {/* Center section */}
        <div className="authz-center">
          {/* Left: Orchestrator label */}
          <motion.div
            className="authz-orchestrator-label"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.3 }}
          >
            <div className="authz-orchestrator-label-text">
              AI<br/>ORCH-<br/>ESTR-<br/>ATOR
            </div>
            <div className="authz-orchestrator-sublabel">Secure Initialization</div>
          </motion.div>

          {/* Center: Steps */}
          <div className="authz-steps">
            <div className="authz-steps-title">Authorization Sequence</div>
            <div className="authz-steps-list">
              {AUTH_STEPS.map((step, i) => (
                <StepLine
                  key={step.id}
                  step={step}
                  index={i}
                  isActive={currentStep === i}
                  isComplete={completedSteps.includes(i)}
                />
              ))}
            </div>
          </div>

          {/* Right: System status */}
          <motion.div
            className="authz-system-status"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.5 }}
          >
            <div className="authz-status-label">System</div>
            <div className="authz-status-items">
              {[
                { label: 'Encryption', value: 'AES-256' },
                { label: 'Protocol', value: 'TLS 1.3' },
                { label: 'Session', value: 'Secure' },
                { label: 'Audit', value: 'Active' },
              ].map((item) => (
                <div key={item.label} className="authz-status-item">
                  <span className="authz-status-item-label">{item.label}</span>
                  <span className="authz-status-item-value">{item.value}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Bottom: entering message */}
        <AnimatePresence>
          {done && (
            <motion.div
              className="authz-entering"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              Entering workspace
              <span className="authz-entering-dots">
                <span /><span /><span />
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
