import React from 'react';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { useAuth } from './context/AuthContext';

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

function ProtectedRoute({ children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<AuthPage />} />
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
            <ProtectedRoute>
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
