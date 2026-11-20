import React, { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Users, Mail, Bot, ShieldCheck, Activity, TrendingUp, BarChart3 } from 'lucide-react';
import Navigation from '../components/Navigation';
import { agentService } from '../services/agentService';
import { useAgentExecution } from '../hooks/useAgentExecution';
import { googleOAuthService } from '../services/googleOAuthService';
import { useAuth } from '../context/AuthContext';
import { ROLES } from '../context/authRoles';

const AGENT_COLOR = '#8B5CF6';

/** Messages one sync may pull. Bounds the work a single click can trigger. */
const SYNC_MAX_RESULTS = 50;

function normalizeFeedbackExecution(execution) {
  const agentResponse = execution?.data;
  const analysis = agentResponse?.data;

  if (
    !execution?.success ||
    agentResponse?.agent !== 'employee_insights' ||
    agentResponse?.operation !== 'extract_feedback' ||
    !analysis ||
    !Array.isArray(analysis.records)
  ) {
    return null;
  }

  return analysis;
}

function normalizeFeedbackPage(response) {
  const page = response?.data;
  const totalPages = page?.pagination?.total_pages;
  if (
    response?.success !== true ||
    !Array.isArray(page?.records) ||
    !Number.isInteger(totalPages) ||
    totalPages < 0
  ) {
    throw new Error('The saved feedback response was invalid.');
  }
  return { records: page.records, totalPages };
}

async function fetchAllFeedback() {
  const pageSize = 100;
  const firstPage = normalizeFeedbackPage(
    await agentService.getEmployeeFeedback(1, pageSize),
  );
  const records = [...firstPage.records];

  for (let page = 2; page <= firstPage.totalPages; page += 1) {
    const nextPage = normalizeFeedbackPage(
      await agentService.getEmployeeFeedback(page, pageSize),
    );
    records.push(...nextPage.records);
  }

  return records;
}

function formatSavedAt(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return 'Timestamp unavailable';

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).formatToParts(date);
  const part = (type) => parts.find((item) => item.type === type)?.value;
  return `${part('day')} ${part('month')} ${part('year')} · ${part('hour')}:${part('minute')} ${part('dayPeriod')?.toUpperCase()}`;
}

function plural(count, singular) {
  return `${count} ${singular}${count === 1 ? '' : 's'}`;
}

function formatSyncResult(result) {
  if (!result) return null;
  if (!result.collected) return 'No messages matched that query.';

  const parts = [`${plural(result.collected, 'email')} synced`];
  parts.push(`${plural(result.saved ?? 0, 'new feedback record')}`);
  if (result.duplicates) parts.push(`${plural(result.duplicates, 'duplicate')} skipped`);
  if (result.skipped) parts.push(`${plural(result.skipped, 'routine message')} ignored`);
  return `${parts.join(' · ')}.`;
}

export default function InsightsAIPage() {
  const { execute, isLoading, error } = useAgentExecution();
  const { hasRole } = useAuth();

  // Gmail is a shared, organisation-wide mailbox. Connecting, reading the
  // status, and syncing are manager-and-above operations on the backend too;
  // hiding the card keeps an employee from clicking into a guaranteed 403.
  const canManageGmail = hasRole(ROLES.MANAGER);

  const [searchParams, setSearchParams] = useSearchParams();
  const [connection, setConnection] = useState(null);
  // 'loading' | 'ready' | 'error'. Kept separate from `connection` so a failed
  // status call can never be mistaken for "still loading" and hang the card.
  const [connectionStatus, setConnectionStatus] = useState('loading');
  const [gmailQuery, setGmailQuery] = useState('');
  const [syncResult, setSyncResult] = useState(null);
  const [syncLoading, setSyncLoading] = useState(false);

  const [emailText, setEmailText] = useState('');
  const [analysisResults, setAnalysisResults] = useState(null);
  const [unpersistedRecords, setUnpersistedRecords] = useState([]);
  const [responseError, setResponseError] = useState(null);
  const [feedbackRecords, setFeedbackRecords] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(null);

  const refreshFeedback = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const records = await fetchAllFeedback();
      setFeedbackRecords(records);
      setHistoryError(null);
      return true;
    } catch (loadError) {
      setHistoryError(loadError?.message || 'Unable to load saved feedback.');
      return false;
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const loadInitialFeedback = async () => {
      try {
        const records = await fetchAllFeedback();
        if (active) {
          setFeedbackRecords(records);
          setHistoryError(null);
        }
      } catch (loadError) {
        if (active) {
          setHistoryError(loadError?.message || 'Unable to load saved feedback.');
        }
      } finally {
        if (active) setHistoryLoading(false);
      }
    };

    loadInitialFeedback();
    return () => {
      active = false;
    };
  }, []);

  const loadConnection = useCallback(async () => {
    setConnectionStatus('loading');
    try {
      const response = await googleOAuthService.status();
      setConnection(response?.data ?? null);
      setConnectionStatus('ready');
    } catch {
      // A failed read is an error state, not a loading one; leaving it as
      // "loading" would strand the card on "Loading connection status…".
      setConnection(null);
      setConnectionStatus('error');
    }
  }, []);

  // Clear the callback query param so a reload does not re-announce the result.
  useEffect(() => {
    const oauthResult = searchParams.get('gmail');
    if (!oauthResult) return;

    setResponseError(
      oauthResult === 'success'
        ? null
        : 'Gmail connection failed. Please try connecting again.'
    );
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams]);

  // Only managers read the shared mailbox status, so an employee never fires
  // a request the backend refuses with a 403.
  useEffect(() => {
    if (canManageGmail) loadConnection();
  }, [canManageGmail, loadConnection]);
  const handleAnalyze = async () => {
    if (!emailText.trim() || isLoading || historyLoading) return;

    setAnalysisResults(null);
    setUnpersistedRecords([]);
    setResponseError(null);
    const result = await execute('employee_insights', 'extract_feedback', {
      email_text: emailText,
    });

    if (!result.success) return;

    const analysis = normalizeFeedbackExecution(result);
    if (!analysis) {
      setResponseError('The analysis response did not contain feedback records.');
      return;
    }

    setAnalysisResults(analysis);
    const persistedRecords = analysis.records.filter(
      (record) => record.saved === true || record.duplicate === true,
    );
    const unsavedRecords = analysis.records.some(
      (record) => record.saved !== true && record.duplicate !== true,
    );
    if (unsavedRecords) {
      setUnpersistedRecords(
        analysis.records.filter(
          (record) => record.saved !== true && record.duplicate !== true,
        ),
      );
      setResponseError('Analysis completed, but feedback could not be confirmed as saved. Your text is preserved.');
      return;
    }

    if (analysis.records.length === 0) return;
    setEmailText('');
    const refreshed = await refreshFeedback();
    if (!refreshed && persistedRecords.length > 0) {
      setFeedbackRecords((current) => {
        const existingIds = new Set(current.map((record) => record.id).filter(Boolean));
        const newRecords = persistedRecords.filter(
          (record) => !record.id || !existingIds.has(record.id),
        );
        return [...newRecords, ...current];
      });
    }
  };

  const handleConnectGmail = async () => {
    if (syncLoading) return;
    try {
      const result = await googleOAuthService.authorize();
      const url = result?.data?.authorization_url;
      if (url) {
        window.location.href = url;
      }
    } catch (connectError) {
      setResponseError(
        connectError?.message || 'Unable to start the Gmail connection.'
      );
    }
  };

  const handleDisconnect = async () => {
    try {
      await googleOAuthService.disconnect();
      setConnection(null);
      setConnectionStatus('ready');
      setSyncResult(null);
      setResponseError(null);
      await refreshFeedback();
    } catch (disconnectError) {
      setResponseError(
        disconnectError?.message || 'Unable to disconnect Gmail.'
      );
    }
  };

  const handleSyncGmail = async () => {
    if (syncLoading) return;
    setSyncLoading(true);
    setSyncResult(null);
    setResponseError(null);
    try {
      // Sync is an Employee Insights operation, so it goes through the same
      // agent endpoint as extraction and carries the caller's role with it.
      const payload = { max_results: SYNC_MAX_RESULTS };
      const query = gmailQuery.trim();
      if (query) payload.query = query;

      const result = await agentService.executeAgent(
        'employee_insights',
        'sync_gmail',
        payload
      );
      setSyncResult(result?.data?.data ?? null);
      await refreshFeedback();
    } catch (syncError) {
      setResponseError(syncError?.message || 'Gmail sync failed.');
    } finally {
      setSyncLoading(false);
    }
  };

  const records = feedbackRecords;
  const sentimentCounts = records.reduce(
    (acc, r) => {
      const sentiment = typeof r.sentiment === 'string' ? r.sentiment.toUpperCase() : '';
      if (sentiment === 'POSITIVE' || sentiment === 'NEGATIVE' || sentiment === 'NEUTRAL') {
        acc[sentiment] += 1;
      }
      return acc;
    },
    { POSITIVE: 0, NEGATIVE: 0, NEUTRAL: 0 },
  );
  const totalRecords = records.length;
  const displayedError = responseError || error || historyError;

  return (
    <div className="saas-workbench">
      <Navigation />
      <main className="saas-main-container">
        <div className="saas-page-body">
          {/* Page Header */}
          <div className="saas-page-header">
            <div className="saas-page-title-wrap">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <Bot size={20} style={{ color: AGENT_COLOR }} />
                <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#22c55e', fontWeight: 600, fontFamily: 'JetBrains Mono, monospace' }}>
                  AI-powered
                </span>
              </div>
              <h1 className="saas-page-title">Employee Feedback Intelligence</h1>
              <p className="saas-page-subtitle">
                Extract, attribute, and score employee feedback from email
                communications using RoBERTa sentiment analysis.
              </p>
            </div>
            <Link to="/agents" className="saas-btn saas-btn-secondary">
              <span style={{ marginRight: 6 }}><Users size={14} /></span>
              Back to Agents
            </Link>
          </div>

          {/* Supported Sources Card */}
          <div className="saas-card" style={{ marginBottom: 24 }}>
            <div className="saas-card-header">
              <div className="saas-card-title">
                <Mail size={16} style={{ color: AGENT_COLOR, marginRight: 8 }} />
                Supported Sources
              </div>
              <ShieldCheck size={14} style={{ color: '#22c55e' }} />
            </div>
            <div className="saas-card-body">
              <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.65)', marginBottom: 12, lineHeight: 1.5 }}>
                Employee Insights analyzes email text you provide. No emails are
                sent, modified, or deleted. All results are scoped to your
                organization.
              </p>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: 'rgba(255,255,255,0.8)' }}>
                  <Activity size={12} style={{ color: AGENT_COLOR }} />
                  <span>Pasted email text</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: 'rgba(255,255,255,0.8)' }}>
                  <Mail size={12} style={{ color: AGENT_COLOR }} />
                  <span>.txt / .eml upload (fallback)</span>
                </div>
              </div>
            </div>
          </div>

          {/* Gmail Connection Card — managers and administrators only */}
          {canManageGmail && (
            <div className="saas-card" style={{ marginBottom: 24 }}>
              <div className="saas-card-header">
                <div className="saas-card-title">
                  <Mail size={16} style={{ color: AGENT_COLOR, marginRight: 8 }} />
                  Gmail Connection
                </div>
                {connection?.connected ? (
                  <span
                    style={{
                      fontSize: '0.7rem',
                      color: '#22c55e',
                      fontWeight: 600,
                      padding: '2px 8px',
                      background: 'rgba(34,197,94,0.1)',
                      borderRadius: 4,
                    }}
                  >
                    CONNECTED
                  </span>
                ) : null}
              </div>
              <div className="saas-card-body">
                {connectionStatus === 'loading' && (
                  <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.65)' }}>
                    Loading connection status…
                  </p>
                )}

                {connectionStatus === 'error' && (
                  <>
                    <p
                      style={{
                        fontSize: '0.85rem',
                        color: '#fca5a5',
                        marginBottom: 12,
                        lineHeight: 1.5,
                      }}
                    >
                      Could not load the Gmail connection status.
                    </p>
                    <button
                      type="button"
                      className="saas-btn saas-btn-secondary"
                      onClick={loadConnection}
                      style={{
                        width: 'fit-content',
                        padding: '10px 20px',
                      }}
                    >
                      Retry
                    </button>
                  </>
                )}

                {connectionStatus === 'ready' && !connection?.connected && (
                  <>
                    <p
                      style={{
                        fontSize: '0.85rem',
                        color: 'rgba(255,255,255,0.65)',
                        marginBottom: 12,
                        lineHeight: 1.5,
                      }}
                    >
                      Connect your organisation's Gmail mailbox to collect employee
                      feedback directly from email. Read-only: no mail is sent,
                      modified, or deleted.
                    </p>
                    <button
                      type="button"
                      className="saas-btn saas-btn-primary"
                      onClick={handleConnectGmail}
                      disabled={isLoading || historyLoading}
                      style={{
                        width: 'fit-content',
                        padding: '10px 20px',
                      }}
                    >
                      Connect Gmail
                    </button>
                  </>
                )}

                {connection?.connected && (
                  <>
                    <p
                      style={{
                        fontSize: '0.85rem',
                        color: 'rgba(255,255,255,0.65)',
                        marginBottom: 12,
                      }}
                    >
                      Connected mailbox: <strong>{connection.gmail_address}</strong>
                    </p>
                    <label
                      htmlFor="gmail-sync-query"
                      style={{
                        display: 'block',
                        maxWidth: 560,
                        fontSize: '0.75rem',
                        color: 'rgba(255,255,255,0.6)',
                        marginBottom: 12,
                      }}
                    >
                      Gmail query (optional — blank uses the 30-day default)
                      <input
                        id="gmail-sync-query"
                        type="text"
                        className="saas-input"
                        placeholder="newer_than:30d -in:spam -in:trash"
                        value={gmailQuery}
                        onChange={(event) => setGmailQuery(event.target.value)}
                        disabled={syncLoading}
                        style={{ marginTop: 4 }}
                      />
                    </label>
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className="saas-btn saas-btn-secondary"
                        onClick={handleSyncGmail}
                        disabled={syncLoading}
                        style={{ padding: '8px 16px' }}
                      >
                        {syncLoading ? 'Syncing…' : 'Sync Gmail'}
                      </button>
                      <button
                        type="button"
                        className="saas-btn saas-btn-secondary"
                        onClick={handleDisconnect}
                        style={{ padding: '8px 16px' }}
                      >
                        Disconnect
                      </button>
                    </div>
                  </>
                )}

                {syncResult && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: 10,
                      background: 'rgba(34,197,94,0.1)',
                      borderRadius: 4,
                      fontSize: '0.8rem',
                      color: '#86efac',
                    }}
                  >
                    {formatSyncResult(syncResult)}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Error Display */}
          {displayedError && (
            <div
              role="alert"
              className="saas-card"
              style={{ marginBottom: 24, borderColor: 'rgba(239, 68, 68, 0.3)' }}
            >
              <div className="saas-card-body" style={{ padding: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <ShieldCheck size={14} style={{ color: '#f87171', marginTop: 2 }} />
                  <span style={{ fontSize: '0.85rem', color: '#fca5a5' }}>
                    {typeof displayedError === 'string'
                      ? displayedError
                      : displayedError?.message || 'Analysis failed. Please try again.'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Email Analysis Section */}
          <div className="saas-card" style={{ marginBottom: 24 }}>
            <div className="saas-card-header">
              <div className="saas-card-title">
                <Mail size={16} style={{ color: AGENT_COLOR, marginRight: 8 }} />
                Analyze Email Feedback
              </div>
            </div>
            <div className="saas-card-body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 720 }}>
                <textarea
                  className="saas-textarea"
                  placeholder="Paste email content to analyze employee feedback sentiment…"
                  value={emailText}
                  onChange={(e) => setEmailText(e.target.value)}
                  rows={6}
                  style={{ minHeight: 120 }}
                />
                <button
                  type="button"
                  className="saas-btn saas-btn-primary"
                  onClick={handleAnalyze}
                  disabled={isLoading || historyLoading || !emailText.trim()}
                  style={{ width: 'fit-content', padding: '10px 24px' }}
                >
                  {isLoading ? (
                    <>
                      <span style={{ marginRight: 8 }}><Bot size={14} /></span>
                      Analyzing…
                    </>
                  ) : (
                    <>
                      <span style={{ marginRight: 8 }}><SendIcon size={14} /></span>
                      Analyze Feedback
                    </>
                  )}
                </button>
                {isLoading && (
                  <p role="status" aria-live="polite" style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.7)', margin: 0 }}>
                    Analyzing feedback…
                  </p>
                )}
                {!isLoading && !emailText.trim() && !analysisResults && (
                  <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', margin: 0 }}>
                    Paste email content above to extract and classify employee feedback.
                  </p>
                )}
              </div>
            </div>
          </div>

          {historyLoading && (
            <p role="status" aria-live="polite" style={{ color: 'rgba(255,255,255,0.7)', margin: '0 0 16px' }}>
              Loading saved feedback…
            </p>
          )}

          {unpersistedRecords.length > 0 && (
            <div className="saas-card" style={{ marginBottom: 24, borderColor: 'rgba(251, 191, 36, 0.35)' }}>
              <div className="saas-card-header">
                <div className="saas-card-title">Analysis results not saved</div>
              </div>
              <div className="saas-card-body">
                {unpersistedRecords.map((record, index) => (
                  <article key={`${record.employee_id || record.employee_name}-${index}`} style={{ marginBottom: 12 }}>
                    <div style={{ color: '#f4f4f5', fontWeight: 600 }}>{record.employee_name}</div>
                    <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: '0.75rem' }}>
                      {record.employee_email || 'Email unavailable'}
                    </div>
                    <p style={{ color: '#e4e4e7', margin: '8px 0' }}>{record.feedback}</p>
                    <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.75rem' }}>
                      {record.sentiment}
                      {typeof record.confidence === 'number' && Number.isFinite(record.confidence)
                        ? ` · Confidence: ${String(record.confidence)}`
                        : ''}
                    </span>
                  </article>
                ))}
              </div>
            </div>
          )}

          {/* Sentiment Summary Cards */}
          {analysisResults && (
            <p role="status" aria-live="polite" style={{ color: 'rgba(255,255,255,0.7)', margin: '0 0 16px' }}>
              Analysis complete. {analysisResults.records.length} feedback record{analysisResults.records.length !== 1 ? 's' : ''} found.
            </p>
          )}

          {analysisResults && analysisResults.records.length === 0 && (
            <div className="saas-card" role="status" style={{ marginBottom: 24 }}>
              <div className="saas-card-body">
                No employee feedback records were found in this text.
              </div>
            </div>
          )}

          {!historyLoading && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: 12,
                marginBottom: 24,
              }}
            >
              <SentimentCard
                label="Total Feedback"
                value={totalRecords}
                icon={BarChart3}
                color="rgba(255,255,255,0.5)"
              />
              <SentimentCard
                label="Positive"
                value={sentimentCounts.POSITIVE}
                icon={TrendingUp}
                color="#22c55e"
              />
              <SentimentCard
                label="Negative"
                value={sentimentCounts.NEGATIVE}
                icon={TrendingUp}
                color="#f87171"
              />
              <SentimentCard
                label="Neutral"
                value={sentimentCounts.NEUTRAL}
                icon={Activity}
                color="rgba(255,255,255,0.4)"
              />
            </div>
          )}

          {/* Saved Employee Feedback */}
          {!historyLoading && totalRecords > 0 && (
            <div className="saas-card">
              <div className="saas-card-header">
                <div className="saas-card-title">
                  <Users size={16} style={{ color: AGENT_COLOR, marginRight: 8 }} />
                  Saved Employee Feedback
                </div>
                <span style={{ fontSize: '0.7rem', fontFamily: 'JetBrains Mono, monospace', color: 'rgba(255,255,255,0.5)', background: 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: 3 }}>
                  {totalRecords} record{totalRecords !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="saas-card-body" style={{ padding: 0 }}>
                {records.map((record) => (
                  <article
                    key={record.id}
                    style={{
                      padding: 16,
                      borderBottom: '1px solid rgba(255,255,255,0.08)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
                      <div>
                        <div style={{ fontWeight: 600, color: '#f4f4f5' }}>{record.employee_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.55)' }}>
                          {record.employee_email || 'Email unavailable'}
                        </div>
                      </div>
                      <time
                        dateTime={record.created_at || undefined}
                        style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.55)', textAlign: 'right' }}
                      >
                        {formatSavedAt(record.created_at)}
                      </time>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '12px 0' }}>
                      <span
                        className={`sentiment-badge sentiment-${String(record.sentiment).toLowerCase()}`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          fontFamily: 'JetBrains Mono, monospace',
                          padding: '2px 8px',
                          borderRadius: 4,
                          textTransform: 'uppercase',
                        }}
                      >
                        {record.sentiment}
                      </span>
                      <span
                        aria-label="Confidence score"
                        style={{ fontSize: '0.8rem', fontFamily: 'JetBrains Mono, monospace', color: '#d4d4d8' }}
                      >
                        Confidence: {typeof record.confidence === 'number' && Number.isFinite(record.confidence)
                          ? String(record.confidence)
                          : 'Not provided'}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.85rem', color: '#e4e4e7', lineHeight: 1.5, margin: 0 }}>
                      {record.feedback}
                    </p>
                  </article>
                ))}
              </div>
            </div>
          )}

          {!historyLoading && !displayedError && !isLoading && totalRecords === 0 && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: 48,
                color: 'rgba(255,255,255,0.4)',
                fontSize: '0.85rem',
              }}
            >
              No analysis yet. Paste email content above to get started.
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function SentimentCard({ label, value, icon: Icon, color }) {
  return (
    <div
      className="saas-card"
      style={{
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        borderColor: 'rgba(255,255,255,0.08)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, color: color }}>
          {label}
        </span>
        <Icon size={16} style={{ color }} />
      </div>
      <span style={{ fontSize: '1.75rem', fontWeight: 700, fontFamily: 'Syne, sans-serif', color: '#fafafa' }}>{value}</span>
    </div>
  );
}

function SendIcon({ size }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ display: 'block' }}
    >
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}
