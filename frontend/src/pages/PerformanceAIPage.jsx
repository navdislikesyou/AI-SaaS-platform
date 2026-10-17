import React, { useState } from 'react';
import {
  BarChart3,
  Play,
  Cpu,
  TrendingUp,
  Table,
  CheckCircle2,
  ShieldCheck,
  Target,
  Lightbulb,
  Compass,
  FileSpreadsheet,
} from 'lucide-react';
import Navigation from '../components/Navigation';
import { usePerformanceJob } from '../hooks/usePerformanceJob';
import { PERFORMANCE_OPERATIONS, performanceService } from '../services/performanceService';
import AgentExecutionResult from '../components/AgentExecutionResult';
import FormatInfoBox, { FormatInfoSample } from '../components/FormatInfoBox';

// Exactly the operations the backend job API accepts. No others are implemented.
const OPERATION_OPTIONS = [
  { id: 'load_dataset', label: 'Describe Dataset' },
  { id: 'compute_kpis', label: 'Calculate KPIs' },
  { id: 'compare_periods', label: 'Compare Periods' },
  { id: 'analyze', label: 'Analyze Trends' },
  { id: 'visualize', label: 'Charts' },
];

const STATUS_LABELS = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
};

export default function PerformanceAIPage() {
  const [activeTab, setActiveTab] = useState('playground');
  const [activeOp, setActiveOp] = useState('compute_kpis');
  // Left empty on purpose. The backend reads a server-side file path, so the
  // operator must state it explicitly rather than accept a silent default.
  const [filePath, setFilePath] = useState('');
  // Which chart row is open, or null. A single value guarantees only one chart
  // image is mounted at a time, so at most one PNG is fetched at a time.
  const [expandedArtifact, setExpandedArtifact] = useState(null);
  const [imageErrors, setImageErrors] = useState({});

  const { submit, getExecution } = usePerformanceJob();

  // Read only the selected operation's execution. Each operation owns its own
  // job id, status, result, and error, so switching tabs can never surface
  // another operation's output.
  const { job, jobId, status, result, error, isLoading } = getExecution(activeOp);

  const handleExecute = async (op = activeOp) => {
    if (!filePath.trim()) return;
    if (getExecution(op).isLoading) return;

    // A new Charts job invalidates the open chart for Charts only.
    if (op === 'visualize') {
      setExpandedArtifact(null);
      setImageErrors({});
    }

    await submit(op, filePath.trim());
  };

  const toggleArtifact = (filename) => {
    setExpandedArtifact((current) => (current === filename ? null : filename));
  };

  return (
    <div className="saas-workbench">
      <Navigation />

      <main className="saas-main-container">
        {/* Topbar */}
        <div className="saas-topbar">
          <div className="saas-breadcrumb">
            <span className="saas-breadcrumb-item">Agents</span>
            <span className="saas-breadcrumb-sep">/</span>
            <span className="saas-breadcrumb-active">Performance AI</span>
          </div>

          <div className="saas-topbar-actions">
            <span
              style={{
                fontSize: '0.75rem',
                padding: '4px 10px',
                borderRadius: '4px',
                background: 'rgba(255,90,0,0.1)',
                color: '#FF5A00',
                border: '1px solid rgba(255,90,0,0.25)',
              }}
            >
              Assistant Ready
            </span>
          </div>
        </div>

        {/* Page Body */}
        <div className="saas-page-body">
          {/* Header */}
          <div className="saas-page-header">
            <div className="saas-page-title-wrap">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <BarChart3 size={22} color="#FF5A00" />
                <h1 className="saas-page-title">Performance Insights Assistant</h1>
              </div>
              <p className="saas-page-subtitle">
                Track team velocity, milestone completion, and business KPIs with clear visual summaries.
              </p>
            </div>
          </div>

          {/* Workbench Tabs */}
          <div className="saas-tabs-bar">
            <button
              className={`saas-tab-btn ${activeTab === 'playground' ? 'active' : ''}`}
              onClick={() => setActiveTab('playground')}
            >
              <TrendingUp size={15} />
              <span>Metrics & Trends</span>
            </button>
            <button
              className={`saas-tab-btn ${activeTab === 'datasets' ? 'active' : ''}`}
              onClick={() => setActiveTab('datasets')}
            >
              <Table size={15} />
              <span>Dataset Source</span>
            </button>
            <button
              className={`saas-tab-btn ${activeTab === 'seam' ? 'active' : ''}`}
              onClick={() => setActiveTab('seam')}
            >
              <Cpu size={15} />
              <span>Assistant Info</span>
            </button>
          </div>

          {/* TAB 1: Playground */}
          {activeTab === 'playground' && (
            <div className="saas-workbench-grid">
              <div>
                <div className="saas-card" style={{ marginBottom: '20px' }}>
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <BarChart3 size={16} color="#FF5A00" />
                      <span>Choose an Analysis</span>
                    </div>

                    <div style={{ display: 'flex', gap: '6px' }}>
                      {OPERATION_OPTIONS.map((op) => (
                        <button
                          key={op.id}
                          onClick={() => setActiveOp(op.id)}
                          style={{
                            fontSize: '0.72rem',
                            padding: '3px 10px',
                            borderRadius: '4px',
                            background: activeOp === op.id ? '#FF5A00' : 'rgba(255,255,255,0.05)',
                            color: activeOp === op.id ? '#fff' : 'rgba(255,255,255,0.6)',
                            border: '1px solid rgba(255,255,255,0.1)',
                            cursor: 'pointer',
                          }}
                        >
                          {op.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="saas-card-body">
                    <div className="saas-input-group">
                      <label className="saas-label">Dataset File Path (server-side)</label>
                      <input
                        type="text"
                        className="saas-input"
                        placeholder="performance_agent/data/Financials_standardized.csv"
                        value={filePath}
                        onChange={(e) => setFilePath(e.target.value)}
                        disabled={isLoading}
                      />
                      <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '6px', lineHeight: 1.5 }}>
                        Relative paths resolve from the <code>backend/</code> directory. Supported
                        formats: <code>.csv</code>, <code>.xlsx</code>. The server
                        reads the file directly, so it must already exist on disk.
                      </div>
                    </div>

                    {jobId && (
                      <div
                        style={{
                          marginTop: '12px',
                          padding: '10px 12px',
                          borderRadius: '6px',
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          fontSize: '0.75rem',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                          <span style={{ color: 'rgba(255,255,255,0.5)', fontFamily: 'JetBrains Mono' }}>
                            JOB ID
                          </span>
                          <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5', wordBreak: 'break-all', textAlign: 'right' }}>
                            {jobId}
                          </span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px' }}>
                          <span style={{ color: 'rgba(255,255,255,0.5)', fontFamily: 'JetBrains Mono' }}>
                            STATUS
                          </span>
                          <span
                            style={{
                              fontFamily: 'JetBrains Mono',
                              color: status === 'failed' ? '#F87171' : status === 'completed' ? '#10B981' : '#FF5A00',
                            }}
                          >
                            {STATUS_LABELS[status] || status}
                          </span>
                        </div>
                      </div>
                    )}

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginTop: '12px' }}>
                      <button
                        className="saas-btn"
                        onClick={() => handleExecute(activeOp)}
                        disabled={!filePath.trim() || isLoading}
                        style={{ background: '#FF5A00', color: '#fff', fontWeight: 600, flexShrink: 0 }}
                      >
                        <Play size={14} fill="#fff" />
                        <span>{isLoading ? 'Running Job...' : 'Run Analysis'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Live Backend Job Result Card — scoped to the selected operation */}
                {!job && !error && !isLoading && (
                  <div className="saas-card" style={{ marginTop: '20px' }}>
                    <div className="saas-card-body" style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
                      No result yet for <strong style={{ color: '#FF5A00' }}>{activeOp}</strong>.
                      Run this analysis to generate results.
                    </div>
                  </div>
                )}
                <AgentExecutionResult
                  executionMeta={
                    job
                      ? {
                          agent: 'performance',
                          operation: job.operation,
                          requestId: job.job_id,
                          status: status === 'failed' ? 'error' : 'success',
                          durationMs: job.started_at && job.completed_at ? undefined : undefined,
                        }
                      : null
                  }
                  isLoading={isLoading}
                  error={error}
                  response={job ? { data: job } : null}
                  agentColor="#FF5A00"
                  simulatedData={
                    result?.visualizations?.length ? (                      <div style={{ marginTop: '12px' }}>
                        <div
                          style={{
                            fontSize: '0.72rem',
                            color: 'rgba(255,255,255,0.5)',
                            fontFamily: 'JetBrains Mono',
                            marginBottom: '8px',
                          }}
                        >
                          GENERATED CHARTS ({result.generated})
                        </div>
                        <table className="saas-table">
                          <thead>
                            <tr>
                              <th>Chart</th>
                              <th>File</th>
                              <th>Size</th>
                              <th style={{ width: '28px' }} />
                            </tr>
                          </thead>
                          <tbody>
                            {result.visualizations.map((viz) => {
                              const isExpanded = expandedArtifact === viz.filename;

                              return (
                                <React.Fragment key={viz.filename}>
                                  <tr
                                    onClick={() => toggleArtifact(viz.filename)}
                                    style={{ cursor: 'pointer' }}
                                  >
                                    <td style={{ fontFamily: 'JetBrains Mono', color: '#FF5A00' }}>
                                      {viz.name}
                                    </td>
                                    <td style={{ fontFamily: 'JetBrains Mono' }}>{viz.filename}</td>
                                    <td style={{ fontFamily: 'JetBrains Mono' }}>
                                      {(viz.size_bytes / 1024).toFixed(1)} KB
                                    </td>
                                    <td
                                      style={{
                                        fontFamily: 'JetBrains Mono',
                                        color: 'rgba(255,255,255,0.5)',
                                        textAlign: 'right',
                                      }}
                                    >
                                      {isExpanded ? '▾' : '▸'}
                                    </td>
                                  </tr>
                                  {/* Expanded panel lives inside the table so the
                                      rows below it shift down naturally. */}
                                  {isExpanded && (
                                    <tr>
                                      <td colSpan={4} style={{ padding: '0 0 12px 0' }}>
                                        <div
                                          style={{
                                            padding: '12px',
                                            background: 'rgba(255,255,255,0.02)',
                                            border: '1px solid rgba(255,255,255,0.06)',
                                            borderRadius: '6px',
                                            textAlign: 'center',
                                          }}
                                        >
                                          {imageErrors[viz.filename] ? (
                                            <div
                                              style={{
                                                fontSize: '0.75rem',
                                                color: '#F87171',
                                                padding: '16px 0',
                                              }}
                                            >
                                              Unable to load {viz.filename}.
                                            </div>
                                          ) : (
                                            <img
                                              src={performanceService.artifactUrl(
                                                jobId,
                                                viz.filename,
                                              )}
                                              alt={`${viz.name} chart`}
                                              loading="lazy"
                                              onError={() =>
                                                setImageErrors((prev) => ({
                                                  ...prev,
                                                  [viz.filename]: true,
                                                }))
                                              }
                                              style={{
                                                maxWidth: '100%',
                                                width: 'auto',
                                                height: 'auto',
                                                objectFit: 'contain',
                                                borderRadius: '4px',
                                                background: '#fff',
                                              }}
                                            />
                                          )}
                                        </div>
                                      </td>
                                    </tr>
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </tbody>
                        </table>
                        <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '10px', lineHeight: 1.5 }}>
                          Select a chart to load its image. Charts load on demand,
                          one at a time.
                        </div>
                      </div>
                    ) : null
                  }
                />
              </div>

              {/* Right Column: Seam Specs */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Cpu size={16} color="#FF5A00" />
                      <span>Adapter Specification</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Adapter Class:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>PerformanceAgentAdapter</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Execution Path:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>Background Job</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Timeout Limit:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>None enforced</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Domain Rule:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#FF5A00' }}>Data Analytics Only</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Execution Seam:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#FF5A00' }}>POST /api/v1/performance/jobs</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Dataset Source */}
          {activeTab === 'datasets' && (
            <div className="saas-card">
              <div className="saas-card-header">
                <div className="saas-card-title">
                  <Table size={16} color="#FF5A00" />
                  <span>Dataset Source</span>
                </div>
              </div>

              <div className="saas-card-body" style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.75)', lineHeight: 1.7 }}>
                <p style={{ marginBottom: '14px' }}>
                  The Performance Analyzer reads datasets from the server filesystem. There is no
                  upload endpoint, so a dataset must already exist on disk before a job can read it.
                </p>

                <div className="saas-input-group" style={{ marginBottom: '16px' }}>
                  <label className="saas-label">File Path (server-side)</label>
                  <input
                    type="text"
                    className="saas-input"
                    placeholder="performance_agent/data/Financials_standardized.csv"
                    value={filePath}
                    onChange={(e) => setFilePath(e.target.value)}
                    disabled={isLoading}
                  />
                </div>

                <FormatInfoBox
                  title="Dataset format"
                  accent="#FF5A00"
                  accentRgb="255, 90, 0"
                  examples={[
                    {
                      label: 'Example header row',
                      content: (
                        <div>
                          <FormatInfoSample label="Financials.csv — header only">
                            {`date,sales,profit,units_sold,employee_id,employee_name,department,product,region,customer_segment,sales_channel,sales_target,profit_target`}
                          </FormatInfoSample>
                          <p
                            style={{
                              margin: '8px 0 0',
                              fontSize: '0.7rem',
                              color: 'rgba(255,255,255,0.5)',
                              lineHeight: 1.5,
                            }}
                          >
                            The bundled sample dataset adds year, month, company,
                            business unit, employee role, manager, customer id,
                            country, product id, product category, unit price,
                            gross sales, discount, and cogs &mdash; enough for
                            every operation this assistant supports.
                          </p>
                        </div>
                      ),
                    },
                  ]}
                >
                  <p>
                    <span className="saas-info-req">Required</span>
                    A path the server can open. This assistant has no upload
                    control: the dataset must already exist on the machine running
                    the backend. A relative path resolves from the{' '}
                    <code>backend/</code> directory.
                  </p>
                  <p>
                    <span className="saas-info-req">Required</span>
                    A <code>.csv</code> or <code>.xlsx</code> file. Only the first
                    worksheet of a workbook is read, so split additional sheets
                    into their own file if you need them. Header names are trimmed
                    and lowercased with spaces turned into underscores, so{' '}
                    <code>Sales Channel</code> is read as <code>sales_channel</code>.
                  </p>
                  <p>
                    <span className="saas-info-req">Required</span>
                    Columns are not uniform across operations. Only <code>compare_periods</code>{' '}
                    insists on a <code>date</code> column and fails the job
                    without it, and <code>analyze</code> needs <code>date</code>{' '}
                    for its time section. <code>compute_kpis</code> does not
                    reject a missing column, but it needs <code>sales</code> and{' '}
                    <code>profit</code> to report anything: totals come back empty
                    without them. <code>load_dataset</code> only describes the file,
                    and <code>visualize</code> draws each chart only if that
                    chart&apos;s columns are present.
                  </p>
                  <p>
                    <span className="saas-info-opt">Optional</span>
                    These add analysis rather than unlocking it:{' '}
                    <code>units_sold</code>, <code>gross_sales</code>,{' '}
                    <code>discount</code>, <code>cogs</code>,{' '}
                    <code>sales_target</code>, <code>profit_target</code>, and the
                    dimension columns <code>employee_id</code>,{' '}
                    <code>employee_name</code>, <code>department</code>,{' '}
                    <code>product</code>, <code>region</code>, <code>country</code>,{' '}
                    <code>customer_id</code>, <code>customer_name</code>,{' '}
                    <code>customer_segment</code>, <code>sales_channel</code>. Each
                    section is produced only when its own columns are all
                    present, and a section with missing columns is left out rather
                    than guessed.
                  </p>
                </FormatInfoBox>

                <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)' }}>
                  <div style={{ marginBottom: '8px' }}>Example paths shipped with the repository:</div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontFamily: 'JetBrains Mono', fontSize: '0.75rem' }}>
                    <li>performance_agent/data/Financials_standardized.csv</li>
                    <li>performance_agent/data/Financials.csv</li>
                  </ul>
                </div>

                <div style={{ marginTop: '16px', fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)' }}>
                  <div style={{ marginBottom: '8px' }}>Supported operations:</div>
                  <ul style={{ margin: 0, paddingLeft: '18px', fontFamily: 'JetBrains Mono', fontSize: '0.75rem' }}>
                    {PERFORMANCE_OPERATIONS.map((op) => (
                      <li key={op}>{op}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: What This Assistant Does (User Guide) */}
          {activeTab === 'seam' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Overview Card */}
              <div className="saas-card">
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <BarChart3 size={18} color="#FF5A00" />
                    <span>What the Performance Insights Assistant Does</span>
                  </div>
                </div>
                <div className="saas-card-body" style={{ lineHeight: 1.7, fontSize: '0.88rem', color: 'rgba(255,255,255,0.85)' }}>
                  <p style={{ marginBottom: '14px' }}>
                    The <strong>Performance Insights Assistant</strong> is your dedicated data intelligence partner. It automatically analyzes your business datasets, computes key performance metrics, identifies performance bottlenecks, and provides period-over-period comparisons without requiring complex spreadsheets or SQL queries.
                  </p>
                  <p>
                    Unlike generic AI chat models that can invent numbers, this assistant uses <strong>pure mathematical and statistical computation</strong> — ensuring every calculated KPI, percentage change, and summary is 100% accurate and verifiable.
                  </p>
                </div>
              </div>

              {/* 4 Core Capabilities Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Target size={16} color="#FF5A00" />
                      <span>1. Automated KPI Calculation</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Instantly computes essential metrics such as customer acquisition cost (CAC), churn rate, revenue growth, team task velocity, and ticket resolution times from raw records.
                  </div>
                </div>

                <div className="saas-card-body saas-card">
                  <div className="saas-card-header" style={{ padding: '0 0 12px' }}>
                    <div className="saas-card-title">
                      <TrendingUp size={16} color="#FF5A00" />
                      <span>2. Period-over-Period Comparisons</span>
                    </div>
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Compare performance across months, quarters, or annual cohorts. See exact percentage variations and growth trends to evaluate whether initiatives hit targets.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Lightbulb size={16} color="#FF5A00" />
                      <span>3. Trend & Anomaly Discovery</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Uncovers patterns that manual inspection misses — such as weekly productivity spikes, delayed milestone stages, or shifts in customer engagement.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <FileSpreadsheet size={16} color="#FF5A00" />
                      <span>4. Executive Visual Summaries</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Converts thousands of rows of data into clean, executive-ready metric summaries with key takeaways and structured tables.
                  </div>
                </div>
              </div>

              {/* How to use */}
              <div className="saas-card">
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <Compass size={16} color="#E8FF72" />
                    <span>How to Use This Assistant</span>
                  </div>
                </div>
                <div className="saas-card-body" style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.75)', lineHeight: 1.7 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(255,90,0,0.15)', color: '#FF5A00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        1
                      </span>
                      <span>Go to the <strong>Metrics &amp; Trends</strong> tab and choose what kind of analysis you need (e.g. <em>Calculate KPIs</em> or <em>Compare Periods</em>).</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(255,90,0,0.15)', color: '#FF5A00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        2
                      </span>
                      <span>Enter the server-side path of an existing dataset, for example <em>performance_agent/data/Financials_standardized.csv</em>.</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(255,90,0,0.15)', color: '#FF5A00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        3
                      </span>
                      <span>Click <strong>Run Analysis</strong>. Analysis runs as a background job, so the panel shows the job status while it works and the result once it completes.</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Security & Reliability Badge */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '14px 20px',
                  borderRadius: '10px',
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.2)',
                  fontSize: '0.82rem',
                  color: 'rgba(255,255,255,0.85)',
                }}
              >
                <ShieldCheck size={20} color="#10B981" />
                <span><strong>Accuracy Guarantee:</strong> All computations are performed mathematically over your isolated data. No external model training or data leakage.</span>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
