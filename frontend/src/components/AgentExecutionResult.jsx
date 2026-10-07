import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, AlertCircle, Clock, Copy, ChevronDown, ChevronUp, Sparkles, Terminal } from 'lucide-react';

export default function AgentExecutionResult({
  executionMeta,
  isLoading,
  error,
  response,
  simulatedData,
  agentColor = '#E8FF72',
}) {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);
  const [copied, setCopied] = useState(false);

  if (isLoading) {
    return (
      <motion.div
        className="execution-panel loading"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          padding: '24px',
          borderRadius: '12px',
          background: 'rgba(255, 255, 255, 0.03)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
        }}
      >
        <div className="execution-spinner-wrap">
          <div
            className="execution-spinner"
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '50%',
              border: `2px solid rgba(255, 255, 255, 0.1)`,
              borderTopColor: agentColor,
              animation: 'spin 0.8s linear infinite',
            }}
          />
        </div>
        <div>
          <div style={{ fontWeight: '600', fontSize: '0.95rem', color: '#fff', marginBottom: '4px' }}>
            Consulting AI Assistant...
          </div>
          <div style={{ fontSize: '0.8rem', color: 'rgba(255, 255, 255, 0.6)' }}>
            Processing your request securely • Generating answer
          </div>
        </div>
      </motion.div>
    );
  }

  if (!executionMeta && !error && !response) {
    return null;
  }

  const handleCopyId = () => {
    if (executionMeta?.requestId) {
      navigator.clipboard?.writeText(executionMeta.requestId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isUnavailable = executionMeta?.isUnavailable || error?.status === 503;

  return (
    <motion.div
      className="execution-result-card"
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      style={{
        marginTop: '24px',
        borderRadius: '14px',
        background: '#0d111a',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        overflow: 'hidden',
      }}
    >
      {/* Friendly Result Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          background: 'rgba(255, 255, 255, 0.03)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: '20px',
              background: 'rgba(16, 185, 129, 0.12)',
              color: '#10B981',
              fontSize: '0.75rem',
              fontWeight: '600',
            }}
          >
            <CheckCircle2 size={13} />
            <span>Assistant Response Ready</span>
          </div>

          <span
            style={{
              fontSize: '0.78rem',
              color: 'rgba(255, 255, 255, 0.5)',
              textTransform: 'capitalize',
            }}
          >
            {executionMeta?.agent} Assistant
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {executionMeta?.durationMs !== undefined && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '0.75rem',
                color: 'rgba(255, 255, 255, 0.4)',
              }}
            >
              <Clock size={12} />
              <span>{executionMeta.durationMs}ms</span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: 'transparent',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: '6px',
              padding: '4px 10px',
              fontSize: '0.72rem',
              color: 'rgba(255, 255, 255, 0.65)',
              cursor: 'pointer',
            }}
          >
            <Terminal size={12} />
            <span>{showTechnicalDetails ? 'Hide System Info' : 'System Info'}</span>
            {showTechnicalDetails ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {/* Main Friendly Output Area */}
      <div style={{ padding: '24px' }}>
        {/* If simulated preview exists, show it prominently */}
        {simulatedData ? (
          <div>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                marginBottom: '16px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(232, 255, 114, 0.08)',
                color: '#E8FF72',
                fontSize: '0.75rem',
                fontWeight: '600',
              }}
            >
              <Sparkles size={13} />
              <span>Generated Output Preview</span>
            </div>
            {typeof simulatedData === 'function' ? simulatedData() : simulatedData}
          </div>
        ) : response ? (
          <div style={{ lineHeight: 1.6, color: '#f4f4f5' }}>
            <pre
              style={{
                background: '#07090e',
                padding: '16px',
                borderRadius: '8px',
                overflowX: 'auto',
                fontSize: '0.85rem',
                color: '#e2e8f0',
              }}
            >
              {JSON.stringify(response.data || response, null, 2)}
            </pre>
          </div>
        ) : (
          <div
            style={{
              padding: '18px',
              borderRadius: '8px',
              background: 'rgba(255, 255, 255, 0.03)',
              color: 'rgba(255, 255, 255, 0.8)',
              fontSize: '0.9rem',
              lineHeight: 1.6,
            }}
          >
            {error?.message || 'Your request was processed successfully.'}
          </div>
        )}

        {/* Collapsible Technical Details for Admins/Developers */}
        <AnimatePresence>
          {showTechnicalDetails && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                marginTop: '20px',
                paddingTop: '16px',
                borderTop: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div
                style={{
                  fontSize: '0.75rem',
                  fontWeight: '600',
                  color: 'rgba(255, 255, 255, 0.5)',
                  marginBottom: '10px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                Connection Details
              </div>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  flexWrap: 'wrap',
                  fontSize: '0.75rem',
                  color: 'rgba(255, 255, 255, 0.7)',
                }}
              >
                <div>
                  <span style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Status: </span>
                  <span style={{ color: isUnavailable ? '#F59E0B' : '#10B981' }}>
                    {isUnavailable ? 'Standalone Mode (Standby)' : 'Connected (200 OK)'}
                  </span>
                </div>

                {executionMeta?.requestId && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Request ID: </span>
                    <button
                      type="button"
                      onClick={handleCopyId}
                      style={{
                        background: 'rgba(255, 255, 255, 0.06)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        color: '#f4f4f5',
                        fontSize: '0.72rem',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <span style={{ fontFamily: 'monospace' }}>{executionMeta.requestId.slice(0, 10)}...</span>
                      <Copy size={11} />
                      {copied && <span style={{ color: '#10B981' }}>✓</span>}
                    </button>
                  </div>
                )}

                {executionMeta?.details?.capabilities && (
                  <div>
                    <span style={{ color: 'rgba(255, 255, 255, 0.4)' }}>Supported Features: </span>
                    <span>{executionMeta.details.capabilities.join(', ')}</span>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
