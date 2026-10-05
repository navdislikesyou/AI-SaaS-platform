import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../context/AuthContext';

const navLinks = [
  { label: 'Workspace', href: '/orchestrator' },
  { label: 'AI Agents', href: '/agents' },
  { label: 'Activity', href: '/insights' },
  { label: 'Organization', href: '/organization' },
  { label: 'Settings', href: '/settings' },
];

export default function Navigation() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <>
      {/* Desktop slim sidebar */}
      <nav className="nav-sidebar">
        {/* <div className="nav-logo">
          <Link to="/orchestrator" className="nav-logo-text">AXON</Link>
          <div className="nav-logo-dot" />
        </div> */}

        <div className="nav-links">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              to={link.href}
              className={`nav-link ${location.pathname === link.href ? 'active' : ''}`}
            >
              <span className="nav-link-text">{link.label}</span>
              {location.pathname === link.href && (
                <motion.div
                  className="nav-link-indicator"
                  layoutId="nav-indicator"
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                />
              )}
            </Link>
          ))}
        </div>

        <div className="nav-user">
          <div className="nav-avatar">{user?.avatar}</div>
          <div className="nav-user-info">
            <span className="nav-user-name">{user?.name?.split(' ')[0]}</span>
            <span className="nav-user-role">{user?.role?.split(' ').slice(0,2).join(' ')}</span>
          </div>
          <button className="nav-logout" onClick={handleLogout} title="Sign out">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </nav>

      {/* Mobile header */}
      <header className="nav-mobile-header">
        {/* <Link to="/orchestrator" className="nav-logo-text">AXON</Link> */}
        <button className="nav-mobile-toggle" onClick={() => setMenuOpen(!menuOpen)}>
          <span /><span /><span />
        </button>
      </header>

      {/* Mobile menu */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div
            className="nav-mobile-menu"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
          >
            {navLinks.map((link) => (
              <Link
                key={link.href}
                to={link.href}
                className="nav-mobile-link"
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <button className="nav-mobile-logout" onClick={handleLogout}>Sign Out</button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
