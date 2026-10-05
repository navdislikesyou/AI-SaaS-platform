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
import { useAgentExecution } from '../hooks/useAgentExecution';
import AgentExecutionResult from '../components/AgentExecutionResult';

const SAMPLE_PAYLOADS = [
  { label: 'Compute Q3 Sales KPIs', op: 'compute_kpis', payload: { dataset: 'q3_sales', metric: 'revenue' } },
  { label: 'Compare Periods (Aug vs Sep)', op: 'compare_periods', payload: { period_a: '2026-08', period_b: '2026-09' } },
  { label: 'Analyze Latency Distribution', op: 'analyze', payload: { dataset: 'agent_telemetry', dimension: 'duration_ms' } },
  { label: 'Generate Visual Schema', op: 'visualize', payload: { chart_type: 'timeseries', metric: 'throughput' } },
];

const DATASETS = [
  {
    id: 'ds_01',
    name: 'q3_sales_metrics.csv',
    rows: '14,250',
    columns: '18',
    size: '2.4 MB',
    type: 'Financial',
  },
  {
    id: 'ds_02',
    name: 'agent_dispatch_telemetry.parquet',
    rows: '89,400',
    columns: '12',
    size: '8.1 MB',
    type: 'Operational',
  },
  {
    id: 'ds_03',
    name: 'workforce_utilization.csv',
    rows: '3,800',
    columns: '9',
    size: '640 KB',
    type: 'Resource',
  },
];

export default function PerformanceAIPage() {
  const [activeTab, setActiveTab] = useState('playground');
  const [activeOp, setActiveOp] = useState('compute_kpis');
  const [dataset, setDataset] = useState('q3_sales_metrics');

  const { execute, isLoading, response, error, executionMeta } = useAgentExecution();

  const handleExecute = async (op = activeOp, customPayload = null) => {
    if (isLoading) return;
    const payload = customPayload || {
      dataset,
      metric: 'revenue',
      operation: op,
    };

    // Call real FastAPI backend execution endpoint
    await execute('performance', op, payload);
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
              <span>Connected Data ({DATASETS.length})</span>
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
                      {[
                        { id: 'compute_kpis', label: 'Calculate KPIs' },
                        { id: 'compare_periods', label: 'Compare Periods' },
                        { id: 'analyze', label: 'Analyze Trends' },
                        { id: 'visualize', label: 'Charts' },
                      ].map((op) => (
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
                      <label className="saas-label">Target Dataset / Business Report</label>
                      <input
                        type="text"
                        className="saas-input"
                        placeholder="e.g. q3_sales_metrics, team_velocity, or enterprise_churn..."
                        value={dataset}
                        onChange={(e) => setDataset(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '12px' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {SAMPLE_PAYLOADS.map((sp, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => {
                              setActiveOp(sp.op);
                              handleExecute(sp.op, sp.payload);
                            }}
                            style={{
                              background: 'rgba(255,255,255,0.04)',
                              border: '1px solid rgba(255,255,255,0.08)',
                              borderRadius: '4px',
                              padding: '4px 8px',
                              fontSize: '0.72rem',
                              color: 'rgba(255,255,255,0.7)',
                              cursor: 'pointer',
                            }}
                          >
                            {sp.label}
                          </button>
                        ))}
                      </div>

                      <button
                        className="saas-btn"
                        onClick={() => handleExecute(activeOp)}
                        disabled={!dataset.trim() || isLoading}
                        style={{ background: '#FF5A00', color: '#fff', fontWeight: 600, flexShrink: 0, marginLeft: '12px' }}
                      >
                        <Play size={14} fill="#fff" />
                        <span>{isLoading ? 'Calculating...' : 'Generate Report'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Live Backend Execution Result Card */}
                <AgentExecutionResult
                  executionMeta={executionMeta}
                  isLoading={isLoading}
                  error={error}
                  response={response}
                  agentColor="#FF5A00"
                  simulatedData={
                    <div style={{ marginTop: '12px' }}>
                      <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.5)', fontFamily: 'JetBrains Mono', marginBottom: '8px' }}>
                        STATISTICAL SUMMARY:
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginTop: '10px' }}>
                        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)' }}>
                          <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.5)', fontFamily: 'JetBrains Mono' }}>MEAN DURATION</div>
                          <div style={{ fontSize: '1.25rem', fontFamily: 'Syne', fontWeight: 700, color: '#f4f4f5', marginTop: '4px' }}>14.2ms</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)' }}>
                          <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.5)', fontFamily: 'JetBrains Mono' }}>DISPATCH COUNT</div>
                          <div style={{ fontSize: '1.25rem', fontFamily: 'Syne', fontWeight: 700, color: '#f4f4f5', marginTop: '4px' }}>12,408</div>
                        </div>
                        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)' }}>
                          <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.5)', fontFamily: 'JetBrains Mono' }}>PERCENTILE P99</div>
                          <div style={{ fontSize: '1.25rem', fontFamily: 'Syne', fontWeight: 700, color: '#f4f4f5', marginTop: '4px' }}>28.1ms</div>
                        </div>
                      </div>
                    </div>
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
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Timeout Limit:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>120.0 seconds</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Domain Rule:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#FF5A00' }}>Data Analytics Only</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Execution Seam:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#FF5A00' }}>run(operation, payload)</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Datasets */}
          {activeTab === 'datasets' && (
            <div className="saas-card">
              <div className="saas-card-header">
                <div className="saas-card-title">
                  <Table size={16} color="#FF5A00" />
                  <span>Configured Analytics Datasets</span>
                </div>
              </div>

              <table className="saas-table">
                <thead>
                  <tr>
                    <th>Dataset Identifier</th>
                    <th>Record Count</th>
                    <th>Dimensions</th>
                    <th>Storage Size</th>
                    <th>Domain Type</th>
                  </tr>
                </thead>
                <tbody>
                  {DATASETS.map((ds) => (
                    <tr key={ds.id}>
                      <td style={{ fontWeight: 500, color: '#fafafa' }}>{ds.name}</td>
                      <td style={{ fontFamily: 'JetBrains Mono' }}>{ds.rows} rows</td>
                      <td style={{ fontFamily: 'JetBrains Mono' }}>{ds.columns} cols</td>
                      <td style={{ fontFamily: 'JetBrains Mono' }}>{ds.size}</td>
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
                          {ds.type}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                      <span>Go to the <strong>Metrics & Trends</strong> tab and choose what kind of analysis you need (e.g. <em>Calculate KPIs</em> or <em>Compare Periods</em>).</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(255,90,0,0.15)', color: '#FF5A00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        2
                      </span>
                      <span>Select a sample report from the quick buttons (e.g. <em>Compute Q3 Sales KPIs</em>) or type a dataset identifier.</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(255,90,0,0.15)', color: '#FF5A00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        3
                      </span>
                      <span>Click <strong>Generate Report</strong> to view immediate mathematical figures, metric trends, and summary findings.</span>
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
