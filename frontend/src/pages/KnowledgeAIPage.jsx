import React, { useRef, useState } from 'react';
import { useAgents } from '../hooks/useAgents';
import { useDocumentUpload } from '../hooks/useDocumentUpload';
import { useKnowledgeDocuments } from '../hooks/useKnowledgeDocuments';
import { useLocation } from 'react-router-dom';
import {
  BookOpen,
  Search,
  FileText,
  Upload,
  Cpu,
  ShieldCheck,
  Sparkles,
  Database,
  CheckCircle2,
  Target,
  AlertCircle,
  Compass,
} from 'lucide-react';
import {
  UPLOAD_ACCEPT_ATTRIBUTE,
  SUPPORTED_UPLOAD_LABEL,
} from '../services/knowledgeService';
import Navigation from '../components/Navigation';
import { useAgentExecution } from '../hooks/useAgentExecution';
import AgentExecutionResult from '../components/AgentExecutionResult';

const SAMPLE_QUERIES = [
  'What is our employee leave policy?',
  'How many remote work days are permitted per week?',
  'What is the procedure for expense reimbursement?',
  'What are the security compliance requirements for API keys?',
];

const INGESTED_DOCS_KEY = 'saas_knowledge_ingested_docs';

/**
 * Read documents ingested by server path in a previous session.
 *
 * Uploads are tracked by the backend manifest. This localStorage list remains
 * only for documents indexed through the older `ingest_document` server-path
 * route, which the backend still supports and which already put chunks in the
 * vector store. Dropping it would make those documents disappear from the
 * selector even though they remain queryable.
 *
 * @returns {Array<{filePath: string, timestamp: string, chunkCount?: number}>}
 */
function readIngestedDocs() {
  try {
    const raw = window.localStorage.getItem(INGESTED_DOCS_KEY);

    if (!raw) return [];

    const parsed = JSON.parse(raw);

    if (!Array.isArray(parsed)) return [];

    return parsed.filter((doc) => doc && typeof doc.filePath === 'string');
  } catch {
    return [];
  }
}

/**
 * Record a successful server-path ingestion and persist it.
 *
 * Re-ingesting a path updates its timestamp instead of adding a duplicate.
 *
 * @param {{filePath: string, timestamp: string, chunkCount?: number}} doc
 */
function registerIngestedDoc(doc) {
  const existing = readIngestedDocs().filter((entry) => entry.filePath !== doc.filePath);

  const next = [doc, ...existing];

  try {
    window.localStorage.setItem(INGESTED_DOCS_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable: the list stays in-memory for this session only.
  }

  return next;
}

/**
 * Describe an upload failure in terms the user can act on.
 *
 * The backend returns a specific message for each rejection (wrong type, too
 * large, unreadable, agent offline). Anything it could not classify falls back
 * to the status code, because a bare "Request failed" tells the user nothing.
 *
 * @param {Error|null} error
 * @param {boolean} isUnavailable
 * @returns {string}
 */
function describeUploadError(error, isUnavailable) {
  if (!error) return '';

  if (isUnavailable) {
    return 'The Knowledge Agent is not connected. Start the backend with the agent enabled, then retry.';
  }

  if (error.code === 'VALIDATION_ERROR' && error.message) return error.message;

  if (error.status === 0) {
    return 'Could not reach the backend. Check that the API is running and try again.';
  }

  if (error.status === 504) {
    return 'Indexing timed out. Try a smaller document.';
  }

  if (error.status === 502) {
    return 'The document could not be indexed. Confirm it is a readable, text-based file rather than a scan.';
  }

  return error.message || `Upload failed with status ${error.status}.`;
}

/**
 * Format an ISO timestamp for display, e.g. "06 Oct 2026, 10:55 PM".
 *
 * @param {string} iso
 * @returns {string}
 */
function formatTimestamp(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

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

export default function KnowledgeAIPage() {
  const location = useLocation();

  // Ingestion is the entry point: there is nothing to query until a document
  // has been indexed.
  const [activeTab, setActiveTab] = useState('ingest');
  const [query, setQuery] = useState('');
  const [ingestPath, setIngestPath] = useState('');
  const [ingestedDocs, setIngestedDocs] = useState(readIngestedDocs);
  const [selectedDocId, setSelectedDocId] = useState('');

  // query and ingestion are separate operations with different payload shapes
  // and different result renderings, so each keeps its own state. Sharing one
  // hook made each tab display whichever operation ran last.
  const queryExec = useAgentExecution();
  const ingestExec = useAgentExecution();

  const fileInputRef = useRef(null);
  const {
    selectedFile,
    selectFile,
    isUploading,
    indexedDocument,
    error: uploadError,
    upload,
  } = useDocumentUpload();

  const {
    documents,
    failedDocuments,
    error: documentsError,
    addDocument,
  } = useKnowledgeDocuments();

  const { agents } = useAgents();
  const knowledgeAgent = agents.find((a) => a.id === 'knowledge');
  const knowledgeCapabilities = knowledgeAgent?.capabilities || [];

  // The selector lists uploaded documents plus anything indexed earlier
  // through the server-path route. Both are queryable: the vector store does
  // not care how a document got there.
  const selectorOptions = [
    ...documents.map((doc) => ({
      id: doc.document_id,
      label: doc.filename,
      detail: formatTimestamp(doc.uploaded_at),
      source: 'upload',
    })),
    ...ingestedDocs.map((doc) => ({
      id: doc.filePath,
      label: doc.filePath,
      detail: formatTimestamp(doc.timestamp),
      source: 'server-path',
    })),
  ];

  const selectedDocument = selectorOptions.find((doc) => doc.id === selectedDocId) || null;

  React.useEffect(() => {
    if (location.state?.query) {
      setQuery(location.state.query);
      queryExec.execute('knowledge', 'query', { question: location.state.query });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  const handleSearch = async (customQuery = null) => {
    const text = customQuery || query;
    if (!text.trim() || queryExec.isLoading) return;
    setQuery(text);

    // Backend query takes { question } only. It runs against the Knowledge
    // vector store, so no file_path is sent.
    await queryExec.execute('knowledge', 'query', { question: text });
  };

  const handleFileChange = (event) => {
    const file = event.target.files?.[0] || null;
    selectFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile || isUploading) return;

    const document = await upload();

    // Only a document the backend reports as indexed joins the selector.
    if (document) addDocument(document);
  };

  const handleIngest = async () => {
    if (!ingestPath.trim() || ingestExec.isLoading) return;

    const path = ingestPath.trim();

    // ingest_document requires file_path, not question.
    const result = await ingestExec.execute('knowledge', 'ingest_document', {
      file_path: path,
    });

    // Register only what the backend actually indexed.
    if (result?.success && result?.data?.data?.indexed) {
      setIngestedDocs(
        registerIngestedDoc({
          filePath: path,
          timestamp: new Date().toISOString(),
          chunkCount: result.data.data.chunk_count,
        }),
      );
      setSelectedDocId(path);
    }
  };

  // Unwrap the execute envelope. useAgentExecution stores the full body:
  //   response            -> { success, data: A, message, request_id }
  //   response.data       -> A  = { agent, operation, data: B, duration_ms, ... }
  //   response.data.data  -> B  = { answer, sources } for query,
  //                               { indexed, chunk_count } for ingest_document
  // Each tab reads only its own response, and the operation guard keeps one
  // operation's payload from ever being rendered as the other's.
  const queryOp = queryExec.response?.data;
  const answer =
    queryOp?.operation === 'query' ? queryOp.data?.answer || '' : '';
  const sources =
    queryOp?.operation === 'query' && Array.isArray(queryOp.data?.sources)
      ? queryOp.data.sources
      : [];

  const ingestOp = ingestExec.response?.data;
  const ingestResult =
    ingestOp?.operation === 'ingest_document' ? ingestOp.data : null;

  const uploadErrorMessage = describeUploadError(uploadError, false);
  const indexedDocumentCount = documents.length;

  return (
    <div className="saas-workbench">
      <Navigation />

      <main className="saas-main-container">
        {/* Topbar */}
        <div className="saas-topbar">
          <div className="saas-breadcrumb">
            <span className="saas-breadcrumb-item">Assistants</span>
            <span className="saas-breadcrumb-sep">/</span>
            <span className="saas-breadcrumb-active">Knowledge Assistant</span>
          </div>

          <div className="saas-topbar-actions">
            <span
              style={{
                fontSize: '0.75rem',
                padding: '4px 10px',
                borderRadius: '4px',
                background: 'rgba(232,255,114,0.1)',
                color: '#E8FF72',
                border: '1px solid rgba(232,255,114,0.25)',
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
                <BookOpen size={22} color="#E8FF72" />
                <h1 className="saas-page-title">Knowledge Assistant</h1>
              </div>
              <p className="saas-page-subtitle">
                Ask questions and get instant, cited answers directly from your company handbooks, guides, and policies.
              </p>
            </div>
          </div>

          {/* Workbench Tabs */}
          <div className="saas-tabs-bar">
            <button
              className={`saas-tab-btn ${activeTab === 'query' ? 'active' : ''}`}
              onClick={() => setActiveTab('query')}
            >
              <Search size={15} />
              <span>Ask a Question</span>
            </button>
            <button
              className={`saas-tab-btn ${activeTab === 'ingest' ? 'active' : ''}`}
              onClick={() => setActiveTab('ingest')}
            >
              <Upload size={15} />
              <span>Ingest Document</span>
            </button>
            <button
              className={`saas-tab-btn ${activeTab === 'corpus' ? 'active' : ''}`}
              onClick={() => setActiveTab('corpus')}
            >
              <Database size={15} />
              <span>Company Documents ({indexedDocumentCount})</span>
            </button>
            <button
              className={`saas-tab-btn ${activeTab === 'seam' ? 'active' : ''}`}
              onClick={() => setActiveTab('seam')}
            >
              <Cpu size={15} />
              <span>Assistant Info</span>
            </button>
          </div>

          {/* TAB 1: Query Console */}
          {activeTab === 'query' && (
            <div className="saas-workbench-grid">
              {/* Left Column: Interactive Console */}
              <div>
                <div className="saas-card" style={{ marginBottom: '20px' }}>
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Sparkles size={16} color="#E8FF72" />
                      <span>Ask Your Question</span>
                    </div>

                    <div style={{ display: 'flex', gap: '6px' }}>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          padding: '3px 10px',
                          borderRadius: '4px',
                          background: '#E8FF72',
                          color: '#000',
                          border: '1px solid rgba(255,255,255,0.1)',
                        }}
                      >
                        Ask Question
                      </span>
                    </div>
                  </div>

                  <div className="saas-card-body">
                    <div className="saas-input-group">
                      <label className="saas-label">Ingested Document</label>
                      {selectorOptions.length === 0 ? (
                        <div
                          style={{
                            padding: '14px',
                            borderRadius: '6px',
                            background: 'rgba(255,255,255,0.03)',
                            border: '1px dashed rgba(255,255,255,0.12)',
                            fontSize: '0.78rem',
                            color: 'rgba(255,255,255,0.65)',
                            lineHeight: 1.6,
                          }}
                        >
                          No documents ingested yet. Go to the{' '}
                          <strong>Ingest Document</strong> tab to upload and index a
                          document before asking questions.
                        </div>
                      ) : (
                        <>
                          <select
                            className="saas-input"
                            value={selectedDocId}
                            onChange={(e) => setSelectedDocId(e.target.value)}
                            disabled={queryExec.isLoading}
                          >
                            <option value="">Select an ingested document…</option>
                            {selectorOptions.map((doc) => (
                              <option key={`${doc.source}-${doc.id}`} value={doc.id}>
                                {doc.label} — Indexed: {doc.detail}
                              </option>
                            ))}
                          </select>
                          {selectedDocument && (
                            <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '6px' }}>
                              {selectedDocument.label} — Indexed: {selectedDocument.detail}
                            </div>
                          )}
                          <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '6px' }}>
                            The selection scopes your question in this workflow. The query runs
                            against the Knowledge vector store, so the request payload stays{' '}
                            <code>{'{ question }'}</code>.
                          </div>
                        </>
                      )}
                    </div>

                    <div className="saas-input-group">
                      <label className="saas-label">Type your question below</label>
                      <input
                        type="text"
                        className="saas-input"
                        placeholder="e.g. What embedding model does the platform use?"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        disabled={queryExec.isLoading}
                      />
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '12px' }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {SAMPLE_QUERIES.map((sq, i) => (
                          <button
                            key={i}
                            type="button"
                            onClick={() => handleSearch(sq)}
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
                            {sq}
                          </button>
                        ))}
                      </div>

                      <button
                        className="saas-btn saas-btn-primary"
                        onClick={() => handleSearch()}
                        disabled={!query.trim() || !selectedDocId || queryExec.isLoading}
                        title={
                          !selectedDocId && selectorOptions.length > 0
                            ? 'Select an ingested document first'
                            : undefined
                        }
                        style={{ flexShrink: 0, marginLeft: '12px' }}
                      >
                        <Search size={14} />
                        <span>{queryExec.isLoading ? 'Searching...' : 'Ask Assistant'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Query Execution Result Card — bound to queryExec only */}
                <AgentExecutionResult
                  executionMeta={queryExec.executionMeta}
                  isLoading={queryExec.isLoading}
                  error={queryExec.error}
                  response={queryExec.response}
                  agentColor="#E8FF72"
                  simulatedData={
                    answer ? (
                      <div style={{ marginTop: '12px' }}>
                        <div style={{ fontSize: '0.85rem', color: '#f4f4f5', lineHeight: 1.6, padding: '14px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '16px' }}>
                          {answer}
                        </div>
                        {sources.length > 0 && (
                          <>
                            <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)', fontFamily: 'JetBrains Mono', textTransform: 'uppercase', marginBottom: '8px' }}>
                              CITED CORPUS SOURCES:
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                              {sources.map((src, i) => (
                                <div key={`${src.source}-${src.page}-${i}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', padding: '8px 12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '4px', fontSize: '0.75rem' }}>
                                  <span style={{ wordBreak: 'break-all' }}>{src.source}</span>
                                  <span style={{ color: '#E8FF72', fontFamily: 'JetBrains Mono', flexShrink: 0 }}>
                                    p. {src.page}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </>
                        )}
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
                      <Cpu size={16} color="#E8FF72" />
                      <span>Adapter Specification</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Adapter Class:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>KnowledgeAgentAdapter</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Timeout Limit:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>300.0 seconds</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: '8px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Supported Formats:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#f4f4f5' }}>PDF, DOCX, TXT</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'rgba(255,255,255,0.45)' }}>Vector Store Seam:</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: '#E8FF72' }}>run(operation, payload)</span>
                    </div>
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <ShieldCheck size={16} color="#4A9DC4" />
                      <span>Capabilities Advertised</span>
                    </div>
                  </div>
                  <div className="saas-card-body">
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {knowledgeCapabilities.map((cap) => (
                        <span
                          key={cap}
                          style={{
                            fontFamily: 'JetBrains Mono',
                            fontSize: '0.68rem',
                            padding: '3px 8px',
                            borderRadius: '4px',
                            background: 'rgba(255,255,255,0.04)',
                            border: '1px solid rgba(255,255,255,0.08)',
                            color: '#d4d4d8',
                          }}
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '8px' }}>
                      Read live from <code>GET /api/v1/agents</code>.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

{/* TAB 2: Ingest Document */}
          {activeTab === 'ingest' && (
            <div className="saas-workbench-grid">
              <div>
                <div className="saas-card" style={{ marginBottom: '20px' }}>
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Upload size={16} color="#E8FF72" />
                      <span>Ingest a Document</span>
                    </div>
                  </div>

                  <div className="saas-card-body">
                    <div className="saas-input-group">
                      <label className="saas-label" htmlFor="knowledge-upload-input">
                        Document File
                      </label>

                      <input
                        id="knowledge-upload-input"
                        ref={fileInputRef}
                        type="file"
                        className="saas-input"
                        accept={UPLOAD_ACCEPT_ATTRIBUTE}
                        onChange={handleFileChange}
                        disabled={isUploading}
                      />

                      <div
                        style={{
                          fontSize: '0.7rem',
                          color: 'rgba(255,255,255,0.45)',
                          marginTop: '6px',
                          lineHeight: 1.5,
                        }}
                      >
                        Accepted formats: <code>{SUPPORTED_UPLOAD_LABEL}</code>. The file is
                        stored on the server under a generated name and indexed for
                        question answering. {selectedFile ? (
                          <>
                            Selected: <strong>{selectedFile.name}</strong>{' '}
                            ({formatBytes(selectedFile.size)})
                          </>
                        ) : (
                          'No file selected yet.'
                        )}
                      </div>
                    </div>

                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginTop: '12px',
                      }}
                    >
                      <span
                        style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)' }}
                      >
                        {indexedDocumentCount} indexed document
                        {indexedDocumentCount === 1 ? '' : 's'}
                      </span>
                      <button
                        className="saas-btn"
                        onClick={handleUpload}
                        disabled={!selectedFile || isUploading}
                        style={{ background: '#E8FF72', color: '#000', fontWeight: 600 }}
                      >
                        <Upload size={14} />
                        <span>
                          {isUploading ? 'Uploading & Indexing...' : 'Upload Document'}
                        </span>
                      </button>
                    </div>

                    {isUploading && (
                      <div
                        role="status"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          marginTop: '14px',
                          padding: '10px 14px',
                          borderRadius: '6px',
                          background: 'rgba(232,255,114,0.08)',
                          border: '1px solid rgba(232,255,114,0.25)',
                          fontSize: '0.82rem',
                          color: '#f4f4f5',
                        }}
                      >
                        <span
                          style={{
                            width: '12px',
                            height: '12px',
                            borderRadius: '50%',
                            border: '2px solid rgba(232,255,114,0.35)',
                            borderTopColor: '#E8FF72',
                            animation: 'spin 0.8s linear infinite',
                            flexShrink: 0,
                          }}
                        />
                        <span>
                          Uploading and indexing {selectedFile?.name}. Chunking and
                          embedding can take a moment on large documents.
                        </span>
                      </div>
                    )}

                    {uploadErrorMessage && (
                      <div
                        role="alert"
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          marginTop: '14px',
                          padding: '12px 14px',
                          borderRadius: '6px',
                          background: 'rgba(239,68,68,0.08)',
                          border: '1px solid rgba(239,68,68,0.3)',
                          fontSize: '0.82rem',
                          color: '#fecaca',
                          lineHeight: 1.5,
                        }}
                      >
                        <AlertCircle size={16} color="#EF4444" style={{ flexShrink: 0 }} />
                        <span>{uploadErrorMessage}</span>
                      </div>
                    )}

                    {indexedDocument && !isUploading && (
                      <div
                        role="status"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          marginTop: '14px',
                          padding: '10px 14px',
                          borderRadius: '6px',
                          background: 'rgba(232,255,114,0.08)',
                          border: '1px solid rgba(232,255,114,0.25)',
                          fontSize: '0.82rem',
                          color: '#f4f4f5',
                        }}
                      >
                        <CheckCircle2 size={16} color="#E8FF72" style={{ flexShrink: 0 }} />
                        <span>
                          Indexed &ldquo;{indexedDocument.filename}&rdquo; as{' '}
                          {indexedDocument.chunk_count} chunk
                          {indexedDocument.chunk_count === 1 ? '' : 's'}. Switch to Ask a
                          Question to query it.
                        </span>
                      </div>
                    )}

                    {documentsError && (
                      <div
                        role="alert"
                        style={{
                          marginTop: '14px',
                          padding: '12px 14px',
                          borderRadius: '6px',
                          background: 'rgba(245,158,11,0.08)',
                          border: '1px solid rgba(245,158,11,0.3)',
                          fontSize: '0.78rem',
                          color: '#fde68a',
                          lineHeight: 1.5,
                        }}
                      >
                        Could not load the indexed document list:{' '}
                        {documentsError.message}. Uploads still work.
                      </div>
                    )}
                  </div>
                </div>

                {/* Server-path ingestion, kept for documents indexed before upload existed. */}
                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <FileText size={16} color="#E8FF72" />
                      <span>Ingest by Server Path</span>
                    </div>
                  </div>

                  <div className="saas-card-body">
                    <div className="saas-input-group">
                      <label className="saas-label">File Path (server-side)</label>
                      <input
                        type="text"
                        className="saas-input"
                        placeholder="knowledge_agent/data/documents/example.docx"
                        value={ingestPath}
                        onChange={(e) => setIngestPath(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleIngest()}
                        disabled={ingestExec.isLoading}
                      />
                      <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '6px', lineHeight: 1.5 }}>
                        For operators indexing a document already on the server.
                        Relative paths resolve from the <code>backend/</code> directory.
                        Prefer the upload control above for browser uploads.
                      </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px' }}>
                      <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)' }}>
                        {ingestedDocs.length} document
                        {ingestedDocs.length === 1 ? '' : 's'} indexed from this browser
                      </span>
                      <button
                        className="saas-btn"
                        onClick={handleIngest}
                        disabled={!ingestPath.trim() || ingestExec.isLoading}
                        style={{ background: 'rgba(232,255,114,0.12)', color: '#E8FF72', fontWeight: 600 }}
                      >
                        <Upload size={14} />
                        <span>{ingestExec.isLoading ? 'Ingesting...' : 'Ingest Document'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Ingest Execution Result Card — bound to ingestExec only */}
                <AgentExecutionResult
                  executionMeta={ingestExec.executionMeta}
                  isLoading={ingestExec.isLoading}
                  error={ingestExec.error}
                  response={ingestExec.response}
                  agentColor="#E8FF72"
                  simulatedData={
                    ingestResult ? (
                      <div style={{ marginTop: '12px' }}>
                        <div
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '10px',
                            padding: '10px 14px',
                            borderRadius: '6px',
                            background: ingestResult.indexed
                              ? 'rgba(232,255,114,0.08)'
                              : 'rgba(245,158,11,0.08)',
                            border: `1px solid ${
                              ingestResult.indexed
                                ? 'rgba(232,255,114,0.25)'
                                : 'rgba(245,158,11,0.25)'
                            }`,
                            fontSize: '0.82rem',
                            color: '#f4f4f5',
                          }}
                        >
                          {ingestResult.indexed
                            ? `Indexed ${ingestResult.chunk_count} chunk${
                                ingestResult.chunk_count === 1 ? '' : 's'
                              }`
                            : 'No chunks were produced for this file.'}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: '10px', lineHeight: 1.5 }}>
                          {ingestResult.indexed
                            ? 'Switch to Ask a Question to query the knowledge store.'
                            : 'The file parsed but produced no content. Check that it is a readable PDF, DOCX, or TXT.'}
                        </div>
                      </div>
                    ) : null
                  }
                />
              </div>
            </div>
          )}

          {/* TAB 3: Document Corpus */}
          {activeTab === 'corpus' && (
            <div className="saas-card">
              <div className="saas-card-header">
                <div className="saas-card-title">
                  <Database size={16} color="#E8FF72" />
                  <span>Indexed Document Inventory</span>
                </div>

<button
              className="saas-btn saas-btn-primary"
              onClick={() => setActiveTab('ingest')}
              style={{ padding: '6px 12px', fontSize: '0.75rem' }}
            >
              <Upload size={14} />
              <span>Ingest New Document</span>
            </button>
          </div>

          <div style={{ padding: '12px 20px 0', fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
            Documents this backend instance has ingested. Chunk counts are what
            was committed to the vector store at upload time. Local development
            storage, so this list is not shared across deployments.
          </div>

          {documents.length === 0 && failedDocuments.length === 0 ? (
            <div
              style={{
                padding: '28px 20px',
                fontSize: '0.8rem',
                color: 'rgba(255,255,255,0.55)',
                textAlign: 'center',
              }}
            >
              No documents indexed yet. Use Ingest New Document to upload a PDF,
              DOCX, or TXT file.
            </div>
          ) : (
            <table className="saas-table">
              <thead>
                <tr>
                  <th>Document Name</th>
                  <th>Format</th>
                  <th>Embedded Chunks</th>
                  <th>File Size</th>
                  <th>Status</th>
                  <th>Last Synchronized</th>
                </tr>
              </thead>
              <tbody>
                {[...documents, ...failedDocuments].map((doc) => (
                  <tr key={`${doc.status}-${doc.document_id}`}>
                    <td style={{ fontWeight: 500, color: '#fafafa', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <FileText size={15} color="#E8FF72" />
                      <span>{doc.filename}</span>
                    </td>
                    <td style={{ fontFamily: 'JetBrains Mono' }}>{doc.extension}</td>
                    <td style={{ fontFamily: 'JetBrains Mono' }}>
                      {doc.chunk_count ? `${doc.chunk_count} vectors` : '—'}
                    </td>
                    <td style={{ fontFamily: 'JetBrains Mono' }}>{formatBytes(doc.size_bytes)}</td>
                    <td>
                      <span
                        style={{
                          fontFamily: 'JetBrains Mono',
                          fontSize: '0.65rem',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background:
                            doc.status === 'indexed'
                              ? 'rgba(232,255,114,0.1)'
                              : 'rgba(239,68,68,0.1)',
                          color: doc.status === 'indexed' ? '#E8FF72' : '#fca5a5',
                          border:
                            doc.status === 'indexed'
                              ? '1px solid rgba(232,255,114,0.25)'
                              : '1px solid rgba(239,68,68,0.25)',
                        }}
                      >
                        {doc.status === 'indexed' ? 'Indexed' : 'Failed'}
                      </span>
                    </td>
                    <td style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem' }}>
                      {formatTimestamp(doc.uploaded_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

          {/* TAB 4: What This Assistant Does (User Guide) */}
          {activeTab === 'seam' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Overview Card */}
              <div className="saas-card">
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <BookOpen size={18} color="#E8FF72" />
                    <span>What the Knowledge Assistant Does</span>
                  </div>
                </div>
                <div className="saas-card-body" style={{ lineHeight: 1.7, fontSize: '0.88rem', color: 'rgba(255,255,255,0.85)' }}>
                  <p style={{ marginBottom: '14px' }}>
                    The <strong>Knowledge Assistant</strong> connects directly to your company's uploaded documents, handbooks, guidelines, and policies. Instead of reading through hundreds of PDF pages or searching in shared drives, you can ask questions in natural language and receive immediate answers with <strong>exact source citations</strong>.
                  </p>
                  <p>
                    Every response is grounded in your company's official documents. You can click on the citation to see the exact paragraph and page number where the answer was retrieved.
                  </p>
                </div>
              </div>

              {/* 4 Core Capabilities Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Target size={16} color="#E8FF72" />
                      <span>1. Company Handbook & Policy Q&A</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Instant answers for leave policies, employee benefits, remote work guidelines, expense reimbursement procedures, and IT security protocols.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <CheckCircle2 size={16} color="#E8FF72" />
                      <span>2. Verified Source Attribution</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Every statement references the exact file and section name (e.g. <em>Employee Handbook 2026, Section 4.2</em>), so you never have to guess whether the information is official.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <FileText size={16} color="#E8FF72" />
                      <span>3. Semantic Document Search</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Understands the meaning behind your question. Even if you don't remember the exact corporate terminology, it finds the relevant information effortlessly.
                  </div>
                </div>

                <div className="saas-card">
                  <div className="saas-card-header">
                    <div className="saas-card-title">
                      <Database size={16} color="#E8FF72" />
                      <span>4. Multi-Document Synthesis</span>
                    </div>
                  </div>
                  <div className="saas-card-body" style={{ fontSize: '0.82rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.6 }}>
                    Combines insights across multiple files — such as linking security standards with onboarding checklists — into one coherent summary.
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
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(232,255,114,0.15)', color: '#E8FF72', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        1
                      </span>
                      <span>Go to the <strong>Ingest Document</strong> tab, choose a PDF, DOCX, or TXT file, and click <strong>Upload Document</strong>. The assistant extracts, chunks, and indexes it.</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(232,255,114,0.15)', color: '#E8FF72', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        2
                      </span>
                      <span>Go to <strong>Ask a Question</strong>, select the document you just indexed, type your question or click a quick suggestion.</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                      <span style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(232,255,114,0.15)', color: '#E8FF72', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, flexShrink: 0 }}>
                        3
                      </span>
                      <span>Browse the <strong>Company Documents</strong> tab anytime to see every document this instance has indexed, with chunk counts and status.</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Privacy Guarantee */}
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
                <span><strong>Privacy & Security:</strong> Your documents are isolated to your workspace and encrypted. They are never shared or used to train external public models.</span>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
