import React from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import PageTransition from '../components/PageTransition';

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <PageTransition>
      <div className="landing-page">
        <header className="landing-header">
          <div className="landing-logo">
            {/* <span className="landing-logo-text">AXON</span> */}
            {/* <span className="landing-logo-dot"></span> */}
          </div>
          <nav className="landing-nav">
            <span className="landing-nav-link">Platform</span>
            <span className="landing-nav-link">Solutions</span>
            <span className="landing-nav-link">Enterprise</span>
          </nav>
        </header>

        <main className="landing-hero">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="landing-label">Workspace OS</div>
          </motion.div>

          <h1 className="landing-headline">
            <motion.span
              className="landing-headline-line"
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            >
              Multi-Agent
            </motion.span>
            <motion.span
              className="landing-headline-line landing-headline-muted"
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            >
              SaaS Platform.
            </motion.span>
          </h1>

          <motion.p
            className="landing-sub"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.4 }}
          >
            A unified organizational workspace powered by specialized AI agents. Route tasks, synthesize knowledge, and multiply your workforce.
          </motion.p>

          <motion.button
            className="landing-cta"
            onClick={() => navigate('/login')}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.5 }}
          >
            Get Started <span className="landing-cta-arrow">→</span>
          </motion.button>
        </main>

        <footer className="landing-features">
          <div className="feature-item">
            <span className="feature-num">01</span>
            <span className="feature-text">Centralized Routing</span>
          </div>
          <div className="feature-item">
            <span className="feature-num">02</span>
            <span className="feature-text">Role-based Access</span>
          </div>
          <div className="feature-item">
            <span className="feature-num">03</span>
            <span className="feature-text">Specialized Agents</span>
          </div>
        </footer>
      </div>
    </PageTransition>
  );
}
