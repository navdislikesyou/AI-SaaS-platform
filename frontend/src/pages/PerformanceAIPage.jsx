import React, { useEffect, useState } from 'react';
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
  Upload,
  AlertCircle,
} from 'lucide-react';
import Navigation from '../components/Navigation';
import { usePerformanceJob } from '../hooks/usePerformanceJob';
import { useDatasetUpload } from '../hooks/useDatasetUpload';
import { usePerformanceDatasets } from '../hooks/usePerformanceDatasets';
import { useArtifactPreview } from '../hooks/useArtifactPreview';
import {
  PERFORMANCE_OPERATIONS,
  SAMPLE_DATASET_ID,
  DATASET_UPLOAD_ACCEPT,
  SUPPORTED_DATASET_LABEL,
} from '../services/performanceService';
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

/**
 * Render a byte count for display, e.g. "1.8 MB".
 *
 * @param {number} bytes
 * @returns {string}
 */
function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—';

  if (bytes < 1024) return `${bytes} B`;

  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function PerformanceAIPage() {
  const [activeTab, setActiveTab] = useState('playground');
  const [activeOp, setActiveOp] = useState('compute_kpis');
  // A dataset is named by the id the backend issued, never by a path. The
  // packaged sample is the default so the page is usable before anything is
  // uploaded, which is also what keeps the previous workflow working.
  const [selectedDatasetId, setSelectedDatasetId] = useState(SAMPLE_DATASET_ID);
  // Which chart row is open, or null. A single value guarantees only one chart
  // image is mounted at a time, so at most one PNG is fetched at a time.
  const [expandedArtifact, setExpandedArtifact] = useState(null);

  const { submit, getExecution } = usePerformanceJob();

  const fileInputRef = React.useRef(null);

  const {
    datasets,
    failedDatasets,
    maxUploadBytes,
    isLoading: datasetsLoading,
    error: datasetsError,
    addDataset,
  } = usePerformanceDatasets();

  const {
    selectedFile,
    selectFile,
    isUploading,
    uploadedDataset,
    errorMessage: uploadErrorMessage,
    upload,
  } = useDatasetUpload({ maxBytes: maxUploadBytes });

  // Read only the selected operation's execution. Each operation owns its own
  // job id, status, result, and error, so switching tabs can never surface
  // another operation's output.
  const { job, jobId, status, result, error, isLoading } = getExecution(activeOp);

  // The chart preview. Charts are fetched through the authenticated API client
  // rather than pointed at with an image URL, because the artifact endpoint is
  // scoped to the organization that owns the job.
  const {
    artifactUrls,
    artifactErrors,
    loadArtifact,
    markArtifactFailed,
  } = useArtifactPreview(jobId);

  const selectedDataset = datasets.find((row) => row.dataset_id === selectedDatasetId) || null;

  const handleExecute = async (op = activeOp) => {
    if (!selectedDatasetId) return;
    if (getExecution(op).isLoading) return;

    // A new Charts job invalidates the open chart for Charts only.
    if (op === 'visualize') {
      setExpandedArtifact(null);
    }

    // Only the id travels. The server resolves it to a file it controls, so the
    // selected dataset is exactly the one the job reads.
    await submit(op, undefined, selectedDatasetId);
  };

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null;

    // Reset the input so re-picking the identical file still fires onChange.
    event.target.value = '';

    selectFile(file);
  };

  const handleUpload = async () => {
    const dataset = await upload();

    // Only a dataset the backend reports as stored joins the selector, and it
    // becomes the selection, so the next run analyses what was just uploaded.
    if (dataset) {
      addDataset(dataset);
      setSelectedDatasetId(dataset.dataset_id);
    }
  };

  const toggleArtifact = (filename) => {
    setExpandedArtifact((current) => (current === filename ? null : filename));
  };

  // Fetch the chart that was opened. Only the open chart is fetched, so a list
  // of thirty-nine charts costs one request rather than thirty-nine.
  useEffect(() => {
    if (!expandedArtifact || !jobId) return;

    loadArtifact(expandedArtifact);
  }, [expandedArtifact, jobId, loadArtifact]);

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
                      <label className="saas-label" htmlFor="performance-dataset-select">
                        Dataset to Analyse
                      </label>

                      <select
                        id="performance-dataset-select"
                        className="saas-input"
                        value={selectedDatasetId}
                        onChange={(e) => setSelectedDatasetId(e.target.value)}
                        disabled={isLoading || isUploading}
                      >
                        {datasets.map((dataset) => (
                          <option key={dataset.dataset_id} value={dataset.dataset_id}>
                            {dataset.is_sample
                              ? `Sample dataset — ${dataset.filename}`
                              : `${dataset.filename} — ${dataset.column_count} columns`}
                          </option>
                        ))}
                      </select>

                      <div
                        style={{
                          fontSize: '0.7rem',
                          color: 'rgba(255,255,255,0.45)',
                          marginTop: '6px',
                          lineHeight: 1.5,
                        }}
                      >
                        {datasetsLoading
                          ? 'Loading available datasets...'
                          : selectedDataset
                            ? selectedDataset.is_sample
                              ? `Analysing the packaged sample dataset. Upload your own file below to use your data.`
                              : `Analysing ${selectedDataset.filename} (${formatBytes(
                                  selectedDataset.size_bytes
                                )}, ${selectedDataset.column_count} columns).`
                            : 'No dataset available. Upload one below.'}
                      </div>
                    </div>

                    {/* Upload a dataset from this device */}
                    <div className="saas-input-group">
                      <label className="saas-label" htmlFor="performance-dataset-input">
                        Upload Dataset
                      </label>

                      <div
                        style={{
                          display: 'flex',
                          gap: '10px',
                          alignItems: 'center',
                          flexWrap: 'wrap',
                        }}
                      >
                        <input
                          id="performance-dataset-input"
                          ref={fileInputRef}
                          type="file"
                          className="saas-input"
                          accept={DATASET_UPLOAD_ACCEPT}
                          onChange={handleFileChange}
                          disabled={isUploading}
                          style={{ flex: '1 1 240px', minWidth: 0 }}
                        />

                        <button
                          className="saas-btn"
                          onClick={handleUpload}
                          disabled={!selectedFile || isUploading}
                          style={{
                            background: 'rgba(255,90,0,0.12)',
                            color: '#FF5A00',
                            fontWeight: 600,
                            flexShrink: 0,
                          }}
                        >
                          <Upload size={14} />
                          <span>{isUploading ? 'Uploading...' : 'Upload Dataset'}</span>
                        </button>
                      </div>

                      <div
                        style={{
                          fontSize: '0.7rem',
                          color: 'rgba(255,255,255,0.45)',
                          marginTop: '6px',
                          lineHeight: 1.5,
                        }}
                      >
                        Accepted formats: <code>{SUPPORTED_DATASET_LABEL}</code>, up to{' '}
                        {maxUploadBytes ? formatBytes(maxUploadBytes) : '25 MB'}. Your file is
                        stored on the server under a generated name and becomes
                        selectable immediately.{' '}
                        {selectedFile ? (
                          <>
                            Selected: <strong>{selectedFile.name}</strong>{' '}
                            ({formatBytes(selectedFile.size)})
                          </>
                        ) : (
                          'No file selected yet.'
                        )}
                      </div>

                      {isUploading && (
                        <div
                          role="status"
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            marginTop: '12px',
                            padding: '10px 14px',
                            borderRadius: '6px',
                            background: 'rgba(255,90,0,0.08)',
                            border: '1px solid rgba(255,90,0,0.25)',
                            fontSize: '0.82rem',
                            color: '#f4f4f5',
                            lineHeight: 1.5,
                          }}
                        >
                          <span
                            style={{
                              display: 'inline-block',
                              width: '14px',
                              height: '14px',
                              borderRadius: '50%',
                              border: '2px solid rgba(255,90,0,0.3)',
                              borderTopColor: '#FF5A00',
                              animation: 'spin 0.8s linear infinite',
                              flexShrink: 0,
                            }}
                          />
                          <span>
                            Validating and storing {selectedFile?.name}. The header is
                            read to confirm the dataset is usable.
                          </span>
                        </div>
                      )}

                      {uploadErrorMessage && !isUploading && (
                        <div
                          role="alert"
                          style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '10px',
                            marginTop: '12px',
                            padding: '12px 14px',
                            borderRadius: '6px',
                            background: 'rgba(239,68,68,0.08)',
                            border: '1px solid rgba(239,68,68,0.3)',
                            fontSize: '0.82rem',
                            color: '#fecaca',
                            lineHeight: 1.5,
                          }}
                        >
                          <AlertCircle
                            size={16}
                            color="#EF4444"
                            style={{ flexShrink: 0 }}
                          />
                          <span>{uploadErrorMessage}</span>
                        </div>
                      )}

                      {uploadedDataset && !isUploading && (
                        <div
                          role="status"
                          style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '10px',
                            marginTop: '12px',
                            padding: '12px 14px',
                            borderRadius: '6px',
                            background: 'rgba(16,185,129,0.08)',
                            border: '1px solid rgba(16,185,129,0.25)',
                            fontSize: '0.82rem',
                            color: '#a7f3d0',
                            lineHeight: 1.5,
                          }}
                        >
                          <CheckCircle2
                            size={16}
                            color="#10B981"
                            style={{ flexShrink: 0 }}
                          />
                          <span>
                            Stored &ldquo;{uploadedDataset.filename}&rdquo; with{' '}
                            {uploadedDataset.column_count} columns. It is selected
                            above, so the next run analyses it.
                          </span>
                        </div>
                      )}

                      {datasetsError && (
                        <div
                          role="alert"
                          style={{
                            marginTop: '12px',
                            padding: '10px 14px',
                            borderRadius: '6px',
                            background: 'rgba(245,158,11,0.08)',
                            border: '1px solid rgba(245,158,11,0.25)',
                            fontSize: '0.78rem',
                            color: '#fcd34d',
                            lineHeight: 1.5,
                          }}
                        >
                          Could not load the dataset list: {datasetsError.message}. You
                          can still upload a dataset.
                        </div>
                      )}
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
                        disabled={!selectedDatasetId || isLoading || isUploading}
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
                                          {artifactErrors[viz.filename] ? (
                                            <div
                                              style={{
                                                fontSize: '0.75rem',
                                                color: '#F87171',
                                                padding: '16px 0',
                                              }}
                                            >
                                              {artifactErrors[viz.filename]}
                                            </div>
                                          ) : artifactUrls[viz.filename] ? (
                                            <img
                                              src={artifactUrls[viz.filename]}
                                              alt={`${viz.name} chart`}
                                              loading="lazy"
                                              onError={() =>
                                                markArtifactFailed(
                                                  viz.filename,
                                                  `This chart could not be displayed.`
                                                )
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
                                          ) : (
                                            <div
                                              style={{
                                                fontSize: '0.75rem',
                                                color: 'rgba(255,255,255,0.5)',
                                                padding: '16px 0',
                                              }}
                                            >
                                              Loading {viz.filename}...
                                            </div>
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
                  Upload a dataset from this device in the{' '}
                  <strong>Metrics &amp; Trends</strong> tab. The file is validated
                  on the server, stored under a generated name, and then appears in
                  the dataset selector next to the packaged sample.
                </p>

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
                            {`date,sales,profit,units_sold,sales_target,profit_target,employee_id,employee_name,department,product,region,customer_segment,sales_channel`}
                          </FormatInfoSample>
                          <p
                            style={{
                              margin: '8px 0 0',
                              fontSize: '0.7rem',
                              color: 'rgba(255,255,255,0.5)',
                              lineHeight: 1.5,
                            }}
                          >
                            The packaged sample dataset adds year, month, company,
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
                    A <code>.csv</code> or <code>.xlsx</code> file, at most{' '}
                    {maxUploadBytes ? formatBytes(maxUploadBytes) : '25 MB'}. Legacy{' '}
                    <code>.xls</code> workbooks are refused rather than accepted and
                    failing later, so re-save yours as <code>.xlsx</code> or CSV.
                  </p>
                  <p>
                    <span className="saas-info-req">Required</span>
                    A readable header row. Only the first worksheet of a workbook is
                    read, so split additional sheets into their own file if you need
                    them. Header names are trimmed and lowercased with spaces turned
                    into underscores, so <code>Sales Channel</code> is read as{' '}
                    <code>sales_channel</code>. After upload the selector shows the
                    column names the server actually found.
                  </p>
                  <p>
                    <span className="saas-info-req">Required</span>
                    Columns are not uniform across operations. <code>compare_periods</code>{' '}
                    insists on a <code>date</code> column and fails the job without
                    it, and <code>analyze</code> needs <code>date</code> for its
                    time section. <code>compute_kpis</code> does not reject a missing
                    column, but it needs <code>sales</code> and <code>profit</code>{' '}
                    to report anything. Watch for one interaction: if{' '}
                    <code>employee_name</code> is present, keep{' '}
                    <code>sales_target</code> and <code>profit_target</code> too, or
                    the company analysis stops with an error. <code>load_dataset</code>{' '}
                    only describes the file, and <code>visualize</code> draws each
                    chart only if that chart&apos;s columns are present.
                  </p>
                  <p>
                    <span className="saas-info-opt">Optional</span>
                    These add analysis rather than unlocking it:{' '}
                    <code>units_sold</code>, <code>gross_sales</code>,{' '}
                    <code>discount</code>, <code>cogs</code>, and the dimension
                    columns <code>employee_id</code>, <code>department</code>,{' '}
                    <code>product</code>, <code>region</code>, <code>country</code>,{' '}
                    <code>customer_id</code>, <code>customer_name</code>,{' '}
                    <code>customer_segment</code>, <code>sales_channel</code>. Each
                    section is produced only when its own columns are all present,
                    and a section with missing columns is left out rather than
                    guessed.
                  </p>
                  <p className="saas-info-note">
                    Uploads are kept on the server this page is talking to. They are
                    not shared between deployments, and they are not removed
                    automatically.
                  </p>
                </FormatInfoBox>

                <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.6)' }}>
                  <div style={{ marginBottom: '8px' }}>
                    Datasets available on this server:
                  </div>
                  <table className="saas-table">
                    <thead>
                      <tr>
                        <th>Dataset</th>
                        <th>Format</th>
                        <th>Size</th>
                        <th>Columns</th>
                        <th>Source</th>
                      </tr>
                    </thead>
                    <tbody>
                      {datasets.map((dataset) => (
                        <tr
                          key={dataset.dataset_id}
                          style={
                            dataset.dataset_id === selectedDatasetId
                              ? { background: 'rgba(255,90,0,0.06)' }
                              : undefined
                          }
                        >
                          <td style={{ fontWeight: 500, color: '#fafafa' }}>
                            {dataset.filename}
                          </td>
                          <td style={{ fontFamily: 'JetBrains Mono' }}>
                            {dataset.format}
                          </td>
                          <td style={{ fontFamily: 'JetBrains Mono' }}>
                            {formatBytes(dataset.size_bytes)}
                          </td>
                          <td style={{ fontFamily: 'JetBrains Mono' }}>
                            {dataset.is_sample ? '—' : dataset.column_count}
                          </td>
                          <td>
                            <span
                              style={{
                                fontFamily: 'JetBrains Mono',
                                fontSize: '0.65rem',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                background: 'rgba(255,90,0,0.1)',
                                color: '#FF5A00',
                                border: '1px solid rgba(255,90,0,0.25)',
                              }}
                            >
                              {dataset.is_sample ? 'Packaged sample' : 'Uploaded'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {datasets.length === 1 && (
                    <div style={{ marginTop: '10px', fontSize: '0.72rem', color: 'rgba(255,255,255,0.45)' }}>
                      Only the packaged sample so far. Upload a dataset in Metrics &amp;
                      Trends to analyse your own data.
                    </div>
                  )}

                  {failedDatasets.length > 0 && (
                    <div
                      role="alert"
                      style={{
                        marginTop: '12px',
                        padding: '10px 14px',
                        borderRadius: '6px',
                        background: 'rgba(239,68,68,0.08)',
                        border: '1px solid rgba(239,68,68,0.3)',
                        fontSize: '0.78rem',
                        color: '#fecaca',
                        lineHeight: 1.5,
                      }}
                    >
                      {failedDatasets.length} dataset
                      {failedDatasets.length === 1 ? ' was' : 's were'} rejected and
                      cannot be selected.
                    </div>
                  )}
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
                      <span>Choose the dataset to analyse in <strong>Dataset to Analyse</strong>. The packaged sample is selected by default; upload a <code>.csv</code> or <code>.xlsx</code> file below and it is selected for you.</span>
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
