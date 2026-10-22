import React from 'react';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { useAuth } from './context/AuthContext';
import { AUTH_STATUS, ROLES } from './context/authRoles';

import LandingPage from './pages/LandingPage';
import AuthPage from './pages/AuthPage';
import AuthorizationPage from './pages/AuthorizationPage';
import OrchestratorPage from './pages/OrchestratorPage';
import AgentDirectoryPage from './pages/AgentDirectoryPage';
import HiringAIPage from './pages/HiringAIPage';
import ResearchAIPage from './pages/ResearchAIPage';
import KnowledgeAIPage from './pages/KnowledgeAIPage';
import AutomationAIPage from './pages/AutomationAIPage';
import PerformanceAIPage from './pages/PerformanceAIPage';
import InsightsAIPage from './pages/InsightsAIPage';
import OrganizationPage from './pages/OrganizationPage';
import SettingsPage from './pages/SettingsPage';

/**
 * The screen shown while the session is still being established.
 *
 * A protected route must not redirect during this window: the session is
 * unknown, not absent, and redirecting would bounce a signed-in user to the
 * login screen on every reload.
 */
function SessionLoadingScreen() {
  return (
    <div
      className="auth-page"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
      }}
    >
      <div style={{ textAlign: 'center' }}>
        <div className="auth-loading-dots" style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
          <span /><span /><span />
        </div>
        <p style={{ marginTop: '16px', color: 'rgba(255,255,255,0.5)', fontSize: '0.875rem' }}>
          Restoring your session…
        </p>
      </div>
    </div>
  );
}

/**
 * The screen shown when the user is signed in but lacks the required role.
 *
 * This is a UI boundary, not a security boundary: the backend applies the same
 * rules and refuses the request regardless of what the browser shows.
 */
function AccessDeniedScreen() {
  return (
    <div
      className="agent-page"
      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}
    >
      <div style={{ textAlign: 'center', maxWidth: '420px' }}>
        <h1 className="placeholder-heading" style={{ fontSize: '2.5rem', marginBottom: '16px' }}>
          Not available
        </h1>
        <p className="body-text" style={{ opacity: 0.7 }}>
          Your role does not include access to this area. Ask an organization administrator if you
          need it.
        </p>
      </div>
    </div>
  );
}

/**
 * Guard a route behind a session and, optionally, a role.
 *
 * @param {object} props
 * @param {React.ReactNode} props.children The route content.
 * @param {string} [props.requireRole] The minimum role required.
 */
function ProtectedRoute({ children, requireRole }) {
  const { status, hasRole } = useAuth();
  const location = useLocation();

  if (status === AUTH_STATUS.LOADING) {
    return <SessionLoadingScreen />;
  }

  if (status !== AUTH_STATUS.AUTHENTICATED) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (requireRole && !hasRole(requireRole)) {
    return <AccessDeniedScreen />;
  }

  return children;
}

/**
 * Send an already-signed-in visitor away from the login screen.
 */
function LoginRoute() {
  const { status } = useAuth();

  if (status === AUTH_STATUS.LOADING) {
    return <SessionLoadingScreen />;
  }

  if (status === AUTH_STATUS.AUTHENTICATED) {
    return <Navigate to="/orchestrator" replace />;
  }

  return <AuthPage />;
}

function AppRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginRoute />} />
        <Route
          path="/authorizing"
          element={
            <ProtectedRoute>
              <AuthorizationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/orchestrator"
          element={
            <ProtectedRoute>
              <OrchestratorPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents"
          element={
            <ProtectedRoute>
              <AgentDirectoryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/hiring"
          element={
            <ProtectedRoute>
              <HiringAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/research"
          element={
            <ProtectedRoute>
              <ResearchAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/knowledge"
          element={
            <ProtectedRoute>
              <KnowledgeAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/automation"
          element={
            <ProtectedRoute>
              <AutomationAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/communication"
          element={
            <ProtectedRoute>
              <AutomationAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/performance"
          element={
            <ProtectedRoute>
              <PerformanceAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/insights"
          element={
            <ProtectedRoute>
              <InsightsAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/agents/insights"
          element={
            <ProtectedRoute>
              <InsightsAIPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/organization"
          element={
            <ProtectedRoute requireRole={ROLES.ADMIN}>
              <OrganizationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <>
      <div className="noise-overlay" aria-hidden="true" />
      <AppRoutes />
    </>
  );
}
