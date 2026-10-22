import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  Cpu,
  BookOpen,
  Zap,
  BarChart3,
  Activity,
  Users,
  Settings,
  LogOut,
  Menu,
  X,
  Radio,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { roleLabel } from '../context/authRoles';
import { useSystemHealth } from '../hooks/useSystemHealth';

export default function Navigation() {
  const { user, logout, isAdmin } = useAuth();
  const { isOnline, health } = useSystemHealth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const navSections = [
    {
      title: 'Workspace',
      items: [
        { label: 'AI Command Center', href: '/orchestrator', icon: LayoutDashboard },
        { label: 'AI Assistants', href: '/agents', icon: Cpu, badge: '3 Active' },
      ],
    },
    {
      title: 'Specialized Assistants',
      items: [
        { label: 'Knowledge Assistant', href: '/agents/knowledge', icon: BookOpen, badge: 'Docs & Q&A', color: '#E8FF72' },
        { label: 'Task Automation', href: '/agents/automation', icon: Zap, badge: 'Drafts', color: '#4A9DC4' },
        { label: 'Performance Insights', href: '/agents/performance', icon: BarChart3, badge: 'Analytics', color: '#FF5A00' },
      ],
    },
    {
      title: 'Organization',
      items: [
        { label: 'Activity History', href: '/insights', icon: Activity },
        // User management is an organization-admin capability. Hiding it for
        // other roles keeps the UI honest about what the backend allows.
        ...(isAdmin ? [{ label: 'Team Directory', href: '/organization', icon: Users }] : []),
        { label: 'Preferences', href: '/settings', icon: Settings },
      ],
    },
  ];

  const renderNavContent = () => (
    <>
      {/* Brand Header */}
      <div className="saas-sidebar-brand">
        <Link to="/orchestrator" className="saas-brand-wrap">
          <div className="saas-brand-icon">A</div>
          <div>
            <div className="saas-brand-title">AXON</div>
          </div>
        </Link>
        <span className="saas-brand-version">v{health?.version || '0.1.0'}</span>
      </div>

      {/* Workspace Switcher */}
      <div className="saas-workspace-pill">
        <div className="saas-workspace-name">
          <div className="saas-workspace-dot" />
          <span>{user?.organizationId || 'Your organization'}</span>
        </div>
      </div>

      {/* Navigation Scroll */}
      <div className="saas-nav-scroll">
        {navSections.map((sec) => (
          <div key={sec.title}>
            <div className="saas-nav-section-title">{sec.title}</div>
            <div className="saas-nav-items">
              {sec.items.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    className={`saas-nav-link ${isActive ? 'active' : ''}`}
                    onClick={() => setMobileOpen(false)}
                  >
                    <div className="saas-nav-link-main">
                      <Icon
                        size={16}
                        style={{ color: isActive && item.color ? item.color : undefined }}
                      />
                      <span>{item.label}</span>
                    </div>
                    {item.badge && (
                      <span className="saas-nav-link-badge" style={isActive && item.color ? { color: item.color } : {}}>
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Sidebar Footer: Real Backend Telemetry & User */}
      <div className="saas-sidebar-footer">
        <div
          className="saas-telemetry-badge"
          title={isOnline ? 'All Systems Operational • AI Service Active' : 'AI Service Reconnecting'}
        >
          <div className="saas-telemetry-left">
            <Radio size={12} color={isOnline ? '#E8FF72' : '#ff5a00'} />
            <span>AI Platform</span>
          </div>
          <span style={{ color: isOnline ? '#E8FF72' : '#ff5a00', fontWeight: 600 }}>
            {isOnline ? 'Operational' : 'Offline'}
          </span>
        </div>

        <div className="saas-user-box">
          <div className="saas-user-info">
            <div className="saas-user-avatar">{user?.avatar || 'US'}</div>
            <div className="saas-user-details">
              <span className="saas-user-name">{user?.name || 'Signed in'}</span>
              <span className="saas-user-role">{roleLabel(user?.role)}</span>
            </div>
          </div>
          <button className="saas-signout-btn" onClick={handleLogout} title="Sign Out">
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="saas-sidebar">{renderNavContent()}</aside>

      {/* Mobile Top Bar */}
      <header className="nav-mobile-header" style={{ display: 'none' }}>
        <Link to="/orchestrator" className="saas-brand-wrap">
          <div className="saas-brand-icon">A</div>
          <span className="saas-brand-title">AXON</span>
        </Link>
        <button
          className="saas-signout-btn"
          onClick={() => setMobileOpen(!mobileOpen)}
          style={{ padding: '6px' }}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </header>

      {/* Mobile Drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="saas-sidebar mobile-open"
            initial={{ x: -260 }}
            animate={{ x: 0 }}
            exit={{ x: -260 }}
            transition={{ duration: 0.2 }}
            style={{ zIndex: 100 }}
          >
            {renderNavContent()}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
