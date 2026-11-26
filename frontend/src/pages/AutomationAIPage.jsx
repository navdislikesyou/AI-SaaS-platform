import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Zap,
  Play,
  Mail,
  Calendar,
  Users,
  Search,
  X,
  AlertCircle,
  Loader2,
  Send,
  Clock,
  FileText,
  CheckCircle2,
  Copy,
  Check,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  ArrowRight,
  Info,
  MapPin,
  ExternalLink,
  Filter,
} from 'lucide-react';
import Navigation from '../components/Navigation';
import AgentExecutionResult from '../components/AgentExecutionResult';
import { useAgentExecution } from '../hooks/useAgentExecution';
import { useEmployeeDirectory } from '../hooks/useEmployeeDirectory';
import { apiClient } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { ROLES } from '../context/authRoles';

const TABS = [
  { id: 'draft', label: 'Draft Email', icon: FileText, badge: 'AI Assistant' },
  { id: 'send', label: 'Send Email', icon: Send, badge: 'Verified Send' },
  { id: 'meeting', label: 'Schedule Meeting', icon: Calendar, badge: 'AXON Calendar' },
];

const SUGGESTED_PROMPTS = [
  'Draft an invitation to Friday architecture review at 10 AM with leadership',
  'Prepare a sprint planning email and agenda for the engineering team',
  'Draft follow-up email after Q3 client presentation with next steps',
  'Schedule a quarterly roadmap sync with engineering and product leads',
];

const COMMON_TIMEZONES = [
  'UTC',
  'Asia/Kolkata',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Australia/Sydney',
];

function formatEmployee(emp) {
  const name = emp.full_name || emp.name || 'Unknown';
  const email = emp.email || '';
  const role = emp.role || 'employee';
  return { ...emp, _name: name, _email: email, _role: role };
}

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export default function AutomationAIPage() {
  const { hasRole, user } = useAuth();
  const isManagerOrAdmin = hasRole(ROLES.MANAGER) || hasRole(ROLES.ADMIN);

  const [activeTab, setActiveTab] = useState('draft');

  // Workflow A: Draft Email state
  const [instruction, setInstruction] = useState('');
  const [draftSubjectHint, setDraftSubjectHint] = useState('');
  const [editableDraftSubject, setEditableDraftSubject] = useState('');
  const [editableDraftBody, setEditableDraftBody] = useState('');
  const [draftIsHtml, setDraftIsHtml] = useState(false);
  const [previewMode, setPreviewMode] = useState('formatted'); // 'formatted' | 'raw'
  const [copiedDraft, setCopiedDraft] = useState(false);

  // Workflow B: Send Email state
  const [sendSubject, setSendSubject] = useState('');
  const [sendHtmlBody, setSendHtmlBody] = useState('');
  const [showSendConfirmModal, setShowSendConfirmModal] = useState(false);
  const [sendSuccessResult, setSendSuccessResult] = useState(null);

  // Workflow C: Schedule Meeting state
  const [meetingTitle, setMeetingTitle] = useState('');
  const [meetingDescription, setMeetingDescription] = useState('');
  const [meetingDate, setMeetingDate] = useState('');
  const [meetingStartTime, setMeetingStartTime] = useState('');
  const [meetingEndTime, setMeetingEndTime] = useState('');
  const [meetingTimezone, setMeetingTimezone] = useState(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      return 'UTC';
    }
  });
  const [meetingVenue, setMeetingVenue] = useState('');
  const [meetingResult, setMeetingResult] = useState(null);
  const [meetingError, setMeetingError] = useState(null);
  const [meetingLoading, setMeetingLoading] = useState(false);

  // Meeting invitations
  const [inviteSubject, setInviteSubject] = useState('');
  const [inviteBody, setInviteBody] = useState('');
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteResult, setInviteResult] = useState(null);
  const [inviteError, setInviteError] = useState(null);

  // Recent Meetings listing
  const [recentMeetings, setRecentMeetings] = useState([]);
  const [recentMeetingsLoading, setRecentMeetingsLoading] = useState(false);

  // Directory selection state
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [selectedIds, setSelectedIds] = useState([]);

  // Hooks
  const { employees, isLoading: employeesLoading, error: employeesError, refresh: refreshEmployees } = useEmployeeDirectory();
  const draftExec = useAgentExecution();
  const sendExec = useAgentExecution();

  const normalizedEmployees = useMemo(
    () => (employees || []).map(formatEmployee),
    [employees]
  );

  const roles = useMemo(() => {
    const set = new Set(normalizedEmployees.map((e) => e._role).filter(Boolean));
    return ['all', ...Array.from(set).sort()];
  }, [normalizedEmployees]);

  const filteredEmployees = useMemo(() => {
    const q = search.trim().toLowerCase();
    return normalizedEmployees.filter((e) => {
      const matchesRole = roleFilter === 'all' || e._role === roleFilter;
      const matchesSearch =
        !q ||
        e._name.toLowerCase().includes(q) ||
        e._email.toLowerCase().includes(q) ||
        e._role.toLowerCase().includes(q);
      return matchesRole && matchesSearch;
    });
  }, [normalizedEmployees, search, roleFilter]);

  const selectedEmployees = useMemo(
    () => normalizedEmployees.filter((e) => selectedIds.includes(e.id)),
    [normalizedEmployees, selectedIds]
  );

  // Toggle selection
  const toggleEmployee = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const removeSelected = (id) => setSelectedIds((prev) => prev.filter((x) => x !== id));
  const clearSelection = () => setSelectedIds([]);
  const selectAllFiltered = () => {
    const filteredIds = filteredEmployees.map((e) => e.id);
    setSelectedIds((prev) => Array.from(new Set([...prev, ...filteredIds])));
  };

  // Synchronize draft response into editable preview fields
  useEffect(() => {
    if (draftExec.response?.data?.data) {
      const data = draftExec.response.data.data;
      const isHtml = Boolean(data.html_body);
      setDraftIsHtml(isHtml);

      const generatedSubject = data.subject || (data.meeting?.title ? `Meeting: ${data.meeting.title}` : draftSubjectHint || 'Meeting Invitation');
      const generatedBody = data.html_body || data.email || '';

      setEditableDraftSubject(generatedSubject);
      setEditableDraftBody(generatedBody);
    }
  }, [draftExec.response, draftSubjectHint]);

  // Load recent meetings
  const loadRecentMeetings = useCallback(async () => {
    setRecentMeetingsLoading(true);
    try {
      const res = await apiClient.get('/meetings?limit=10');
      const data = res?.data?.meetings || res?.meetings || [];
      setRecentMeetings(Array.isArray(data) ? data : []);
    } catch {
      setRecentMeetings([]);
    } finally {
      setRecentMeetingsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'meeting') {
      loadRecentMeetings();
    }
  }, [activeTab, loadRecentMeetings]);

  // Copy helper
  const handleCopyDraft = async () => {
    try {
      await navigator.clipboard.writeText(editableDraftBody || '');
      setCopiedDraft(true);
      setTimeout(() => setCopiedDraft(false), 2000);
    } catch {
      // Fallback
    }
  };

  // Transfer draft to Send Email workflow
  const handleTransferToSend = () => {
    setSendSubject(editableDraftSubject);
    setSendHtmlBody(
      draftIsHtml
        ? editableDraftBody
        : `<p>${escapeHtml(editableDraftBody).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br />')}</p>`
    );
    setActiveTab('send');
  };

  // Format local date + time to ISO 8601 with offset
  const toLocalIsoWithOffset = (date, time) => {
    if (!date || !time) return null;
    const dt = new Date(`${date}T${time}`);
    if (Number.isNaN(dt.getTime())) return null;
    const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, '0');
    const tzOffset = -dt.getTimezoneOffset();
    const sign = tzOffset >= 0 ? '+' : '-';
    const hh = pad(tzOffset / 60);
    const mm = pad(tzOffset % 60);
    const yyyy = dt.getFullYear();
    const mo = String(dt.getMonth() + 1).padStart(2, '0');
    const da = String(dt.getDate()).padStart(2, '0');
    const h = String(dt.getHours()).padStart(2, '0');
    const m = String(dt.getMinutes()).padStart(2, '0');
    return `${yyyy}-${mo}-${da}T${h}:${m}:00${sign}${hh}:${mm}`;
  };

  // Execute Draft Action (Plain text)
  const handleDraftAction = async () => {
    const trimmed = instruction.trim();
    if (!trimmed || draftExec.isLoading) return;

    await draftExec.execute('automation', 'draft_action', {
      instruction: trimmed,
      employee_ids: selectedIds.length > 0 ? selectedIds : undefined,
    });
  };

  // Execute Draft HTML
  const handleDraftHtml = async () => {
    const trimmed = instruction.trim();
    if (!trimmed || draftExec.isLoading) return;

    await draftExec.execute('automation', 'draft_html', {
      instruction: trimmed,
      employee_ids: selectedIds.length > 0 ? selectedIds : undefined,
    });
  };

  // Trigger Send Email confirmation modal
  const handleInitiateSend = () => {
    if (!sendSubject.trim() || !sendHtmlBody.trim() || selectedEmployees.length === 0) return;
    setShowSendConfirmModal(true);
  };

  // Execute Confirmed Send Email
  const handleConfirmSendEmail = async () => {
    setShowSendConfirmModal(false);
    setSendSuccessResult(null);

    const idempotencyKey = `ui-send-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const payload = {
      employee_ids: selectedEmployees.map((e) => e.id),
      subject: sendSubject.trim(),
      html_body: sendHtmlBody.trim(),
      confirm: true,
      idempotency_key: idempotencyKey,
    };

    const res = await sendExec.execute('automation', 'send_email', payload);
    if (res?.success) {
      setSendSuccessResult({
        subject: sendSubject.trim(),
        recipientCount: selectedEmployees.length,
        timestamp: new Date().toLocaleTimeString(),
        idempotencyKey,
      });
    }
  };

  // Execute Schedule Meeting
  const handleCreateMeeting = async () => {
    setMeetingError(null);
    setMeetingResult(null);
    setInviteResult(null);
    setInviteError(null);

    if (!meetingTitle.trim() || !meetingDate || !meetingStartTime || !meetingEndTime) {
      setMeetingError({ message: 'Title, date, start time, and end time are required.' });
      return;
    }
    if (selectedEmployees.length === 0) {
      setMeetingError({ message: 'Please select at least one organization employee as attendee.' });
      return;
    }

    const startsAt = toLocalIsoWithOffset(meetingDate, meetingStartTime);
    const endsAt = toLocalIsoWithOffset(meetingDate, meetingEndTime);

    if (!startsAt || !endsAt) {
      setMeetingError({ message: 'Invalid meeting date or time specified.' });
      return;
    }
    if (new Date(endsAt) <= new Date(startsAt)) {
      setMeetingError({ message: 'Meeting end time must be after start time.' });
      return;
    }

    setMeetingLoading(true);
    try {
      const payload = {
        title: meetingTitle.trim(),
        description: meetingDescription.trim() || null,
        starts_at: startsAt,
        ends_at: endsAt,
        timezone: meetingTimezone || 'UTC',
        venue: meetingVenue.trim() || null,
        attendees: selectedEmployees.map((e) => ({
          name: e._name,
          email: e._email,
          user_id: e.id,
        })),
      };

      const res = await apiClient.post('/meetings', payload);
      const created = res?.data || res;
      setMeetingResult(created);

      // Prepare invitation default text
      setInviteSubject(`Invitation: ${created.title}`);
      setInviteBody(
        `<p>You are invited to <strong>${escapeHtml(created.title)}</strong>.</p>` +
        `<p><strong>Date & Time:</strong> ${meetingDate} from ${meetingStartTime} to ${meetingEndTime} (${meetingTimezone})</p>` +
        (meetingVenue ? `<p><strong>Venue:</strong> ${escapeHtml(meetingVenue)}</p>` : '') +
        (meetingDescription ? `<p><strong>Agenda:</strong> ${escapeHtml(meetingDescription)}</p>` : '')
      );

      // Reload recent meetings list
      loadRecentMeetings();
    } catch (err) {
      setMeetingError(err);
    } finally {
      setMeetingLoading(false);
    }
  };

  // Execute Send Meeting Invitation
  const handleConfirmSendInvitation = async () => {
    if (!meetingResult?.id) return;
    setShowInviteModal(false);
    setInviteLoading(true);
    setInviteResult(null);
    setInviteError(null);

    try {
      const res = await apiClient.post(`/meetings/${meetingResult.id}/send-invitation`, {
        subject: inviteSubject.trim() || `Invitation: ${meetingResult.title}`,
        html_body: inviteBody.trim() || `<p>You are invited to <strong>${escapeHtml(meetingResult.title)}</strong>.</p>`,
        confirm: true,
        idempotency_key: `ui-invite-${meetingResult.id}-${Date.now()}`,
      });
      setInviteResult(res?.data || res);
    } catch (err) {
      setInviteError(err);
    } finally {
      setInviteLoading(false);
    }
  };

  // Conditions
  const canDraft = instruction.trim().length > 0 && !draftExec.isLoading;
  const canSend = sendSubject.trim() && sendHtmlBody.trim() && selectedEmployees.length > 0 && !sendExec.isLoading;
  const canSchedule = meetingTitle.trim() && meetingDate && meetingStartTime && meetingEndTime && selectedEmployees.length > 0 && !meetingLoading;

  return (
    <div className="saas-workbench">
      <Navigation />

      <main className="saas-main-container">
        {/* Topbar */}
        <div className="saas-topbar">
          <div className="saas-breadcrumb">
            <Link to="/agents" className="saas-breadcrumb-item">Assistants</Link>
            <span className="saas-breadcrumb-sep">/</span>
            <span className="saas-breadcrumb-active">Task Automation</span>
          </div>

          <div className="saas-topbar-actions">
            <span className="saas-status-chip online" title="Automation Agent Connected">
              <span className="saas-pulse-dot" />
              <span>Assistant Ready</span>
            </span>
          </div>
        </div>

        {/* Page Body */}
        <div className="saas-page-body">
          {/* Header */}
          <div className="saas-page-header">
            <div className="saas-page-title-wrap">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '8px',
                    background: 'rgba(74, 157, 196, 0.15)',
                    border: '1px solid rgba(74, 157, 196, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Zap size={18} color="#4A9DC4" />
                </div>
                <div>
                  <h1 className="saas-page-title">Task Automation Agent</h1>
                </div>
              </div>
              <p className="saas-page-subtitle">
                Draft executive communications, dispatch verified messages to your organization employees, and schedule AXON team meetings.
              </p>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="saas-badge-cyan">
                <ShieldCheck size={13} />
                Strict Organization Isolation
              </span>
            </div>
          </div>

          {/* Workflow Tabs Bar */}
          <div className="saas-tabs-bar">
            {TABS.map(({ id, label, icon: Icon, badge }) => (
              <button
                key={id}
                className={`saas-tab-btn ${activeTab === id ? 'active' : ''}`}
                onClick={() => setActiveTab(id)}
              >
                <Icon size={15} color={activeTab === id ? '#4A9DC4' : undefined} />
                <span>{label}</span>
                <span
                  style={{
                    fontSize: '0.65rem',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    background: activeTab === id ? 'rgba(74, 157, 196, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                    color: activeTab === id ? '#7ad0fa' : 'rgba(255, 255, 255, 0.45)',
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                >
                  {badge}
                </span>
              </button>
            ))}
          </div>

          {/* Workbench Grid: Left Column for Workflow Content, Right Column for Organization Employees */}
          <div className="saas-workbench-grid">
            {/* LEFT COLUMN: ACTIVE WORKFLOW */}
            <div>
              {/* ========================================================= */}
              {/* TAB 1: DRAFT EMAIL WORKFLOW                               */}
              {/* ========================================================= */}
              {activeTab === 'draft' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Draft Input Card */}
                  <div className="saas-card">
                    <div className="saas-card-header">
                      <div className="saas-card-title">
                        <Sparkles size={16} color="#4A9DC4" />
                        <span>Natural Language Email Drafting</span>
                      </div>
                      <span className="saas-badge-cyan">Model: Llama 3</span>
                    </div>

                    <div className="saas-card-body">
                      {/* Safety note */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          padding: '10px 14px',
                          borderRadius: '6px',
                          background: 'rgba(74, 157, 196, 0.07)',
                          border: '1px solid rgba(74, 157, 196, 0.2)',
                          fontSize: '0.78rem',
                          color: 'rgba(255, 255, 255, 0.8)',
                          marginBottom: '16px',
                        }}
                      >
                        <ShieldCheck size={16} color="#4A9DC4" style={{ flexShrink: 0 }} />
                        <span>
                          <strong>Draft-Only Guarantee:</strong> Drafting generates an editable preview. It will never send an email or touch external mailboxes without your explicit confirmation.
                        </span>
                      </div>

                      {/* Prompt input */}
                      <div className="saas-input-group">
                        <label className="saas-label">Drafting Instruction / Prompt</label>
                        <textarea
                          className="saas-textarea"
                          rows={4}
                          placeholder="e.g. Draft an email inviting the engineering leads to tomorrow's 10:00 AM architecture review meeting on microservices migration..."
                          value={instruction}
                          onChange={(e) => setInstruction(e.target.value)}
                        />
                      </div>

                      {/* Prompt suggestion chips */}
                      <div style={{ marginBottom: '16px' }}>
                        <div style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.45)', marginBottom: '8px' }}>
                          Quick prompt templates:
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                          {SUGGESTED_PROMPTS.map((promptText) => (
                            <button
                              key={promptText}
                              type="button"
                              className="saas-prompt-chip"
                              onClick={() => setInstruction(promptText)}
                            >
                              {promptText}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Recipient scope context info */}
                      <div
                        style={{
                          fontSize: '0.75rem',
                          color: 'rgba(255, 255, 255, 0.55)',
                          padding: '8px 12px',
                          borderRadius: '6px',
                          background: 'rgba(255, 255, 255, 0.02)',
                          border: '1px solid rgba(255, 255, 255, 0.06)',
                          marginBottom: '18px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                        }}
                      >
                        <Users size={14} color="#4A9DC4" />
                        <span>
                          {selectedEmployees.length > 0 ? (
                            <>
                              Scoped to <strong>{selectedEmployees.length} selected employee(s)</strong>:{' '}
                              {selectedEmployees.map((e) => e._name).join(', ')}
                            </>
                          ) : (
                            'Recipient names mentioned in your instruction will be resolved against active organization employees.'
                          )}
                        </span>
                      </div>

                      {/* Action buttons */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="saas-btn saas-btn-cyan"
                          disabled={!canDraft}
                          onClick={handleDraftAction}
                        >
                          {draftExec.isLoading ? (
                            <>
                              <Loader2 size={15} className="animate-spin" />
                              <span>Drafting Action...</span>
                            </>
                          ) : (
                            <>
                              <Play size={15} />
                              <span>Generate Draft Action</span>
                            </>
                          )}
                        </button>

                        <button
                          type="button"
                          className="saas-btn saas-btn-secondary"
                          disabled={!canDraft}
                          onClick={handleDraftHtml}
                        >
                          <Mail size={15} color="#4A9DC4" />
                          <span>Generate HTML Draft</span>
                        </button>

                        {instruction.trim() && (
                          <button
                            type="button"
                            className="saas-btn saas-btn-secondary"
                            onClick={() => setInstruction('')}
                          >
                            Clear
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Draft Results & Editable Preview Card */}
                  {draftExec.response?.data?.data && (
                    <div className="saas-card">
                      <div className="saas-card-header">
                        <div className="saas-card-title">
                          <CheckCircle2 size={16} color="#22c55e" />
                          <span>Generated Draft Preview</span>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <button
                            type="button"
                            className="saas-btn saas-btn-secondary"
                            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                            onClick={() => setPreviewMode(previewMode === 'formatted' ? 'raw' : 'formatted')}
                          >
                            {previewMode === 'formatted' ? 'View Raw' : 'View Formatted'}
                          </button>

                          <button
                            type="button"
                            className="saas-btn saas-btn-secondary"
                            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                            onClick={handleCopyDraft}
                          >
                            {copiedDraft ? <Check size={14} color="#22c55e" /> : <Copy size={14} />}
                            <span>{copiedDraft ? 'Copied' : 'Copy'}</span>
                          </button>

                          <button
                            type="button"
                            className="saas-btn saas-btn-cyan"
                            style={{ padding: '4px 12px', fontSize: '0.75rem' }}
                            onClick={handleTransferToSend}
                          >
                            <Send size={13} />
                            <span>Transfer to Send Email</span>
                            <ArrowRight size={13} />
                          </button>
                        </div>
                      </div>

                      <div className="saas-card-body">
                        {/* Editable Subject */}
                        <div className="saas-input-group">
                          <label className="saas-label">Email Subject</label>
                          <input
                            type="text"
                            className="saas-input"
                            value={editableDraftSubject}
                            onChange={(e) => setEditableDraftSubject(e.target.value)}
                            placeholder="Email Subject"
                          />
                        </div>

                        {/* Editable Body */}
                        <div className="saas-input-group">
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                            <label className="saas-label" style={{ margin: 0 }}>
                              {draftIsHtml ? 'HTML Email Body (Editable)' : 'Email Body (Editable)'}
                            </label>
                            <span style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.45)' }}>
                              Review and edit text before sending
                            </span>
                          </div>

                          {previewMode === 'formatted' && draftIsHtml ? (
                            <div className="saas-preview-box">
                              <div className="saas-preview-header-row">
                                <span className="saas-preview-header-label">Subject</span>
                                <span className="saas-preview-header-value">{editableDraftSubject || '(No subject)'}</span>
                              </div>
                              <div
                                className="saas-preview-body-content"
                                dangerouslySetInnerHTML={{ __html: editableDraftBody }}
                              />
                            </div>
                          ) : (
                            <textarea
                              className="saas-textarea"
                              rows={10}
                              style={{ fontFamily: draftIsHtml ? 'JetBrains Mono, monospace' : 'Inter, sans-serif', fontSize: '0.85rem' }}
                              value={editableDraftBody}
                              onChange={(e) => setEditableDraftBody(e.target.value)}
                            />
                          )}
                        </div>

                        {/* Matched Recipients Badge List */}
                        {Array.isArray(draftExec.response.data.data.recipients) &&
                          draftExec.response.data.data.recipients.length > 0 && (
                            <div style={{ marginTop: '14px' }}>
                              <label className="saas-label">Matched Organization Recipients</label>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                                {draftExec.response.data.data.recipients.map((r, idx) => (
                                  <span key={idx} className="saas-recipient-chip">
                                    <Users size={12} />
                                    <span>{r.name || r.email}</span>
                                    {r.email && <span style={{ opacity: 0.6 }}>&lt;{r.email}&gt;</span>}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                        {/* Parsed Meeting Information (if any) */}
                        {draftExec.response.data.data.meeting?.title && (
                          <div
                            style={{
                              marginTop: '16px',
                              padding: '12px 14px',
                              borderRadius: '8px',
                              background: 'rgba(255, 255, 255, 0.03)',
                              border: '1px solid rgba(255, 255, 255, 0.08)',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 600, color: '#f4f4f5' }}>
                                <Calendar size={15} color="#4A9DC4" />
                                <span>Parsed Meeting: {draftExec.response.data.data.meeting.title}</span>
                              </div>
                              <button
                                type="button"
                                className="saas-btn saas-btn-secondary"
                                style={{ padding: '3px 8px', fontSize: '0.72rem' }}
                                onClick={() => {
                                  setMeetingTitle(draftExec.response.data.data.meeting.title || '');
                                  if (draftExec.response.data.data.meeting.venue) {
                                    setMeetingVenue(draftExec.response.data.data.meeting.venue);
                                  }
                                  setActiveTab('meeting');
                                }}
                              >
                                Pre-fill Schedule Meeting
                              </button>
                            </div>
                            <div style={{ display: 'flex', gap: '16px', fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)' }}>
                              {draftExec.response.data.data.meeting.date && (
                                <span>Date: {draftExec.response.data.data.meeting.date}</span>
                              )}
                              {draftExec.response.data.data.meeting.time && (
                                <span>Time: {draftExec.response.data.data.meeting.time}</span>
                              )}
                              {draftExec.response.data.data.meeting.venue && (
                                <span>Venue: {draftExec.response.data.data.meeting.venue}</span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Telemetry / Result Container */}
                  <AgentExecutionResult
                    isLoading={draftExec.isLoading}
                    response={draftExec.response}
                    error={draftExec.error}
                    executionMeta={draftExec.executionMeta}
                  />
                </div>
              )}

              {/* ========================================================= */}
              {/* TAB 2: SEND EMAIL WORKFLOW                                */}
              {/* ========================================================= */}
              {activeTab === 'send' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Send Email Form Card */}
                  <div className="saas-card">
                    <div className="saas-card-header">
                      <div className="saas-card-title">
                        <Send size={16} color="#4A9DC4" />
                        <span>Verified Email Dispatch</span>
                      </div>
                      <span className="saas-badge-amber">
                        <ShieldCheck size={12} />
                        Manager / Admin Required
                      </span>
                    </div>

                    <div className="saas-card-body">
                      {/* Notice Banner */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          padding: '12px 16px',
                          borderRadius: '8px',
                          background: 'rgba(245, 158, 11, 0.08)',
                          border: '1px solid rgba(245, 158, 11, 0.25)',
                          fontSize: '0.8rem',
                          color: '#fef3c7',
                          marginBottom: '20px',
                        }}
                      >
                        <AlertCircle size={18} color="#f59e0b" style={{ flexShrink: 0 }} />
                        <div>
                          <strong>Strict Verification & Confirmation:</strong> Sending triggers real email dispatch via your organization's authenticated Gmail connection. Recipients must be active organization employees selected from the directory.
                        </div>
                      </div>

                      {/* Recipient Selection Display */}
                      <div className="saas-input-group">
                        <label className="saas-label">Recipients ({selectedEmployees.length} selected)</label>
                        {selectedEmployees.length === 0 ? (
                          <div
                            style={{
                              padding: '14px',
                              borderRadius: '6px',
                              background: 'rgba(255, 255, 255, 0.02)',
                              border: '1px dashed rgba(255, 255, 255, 0.15)',
                              fontSize: '0.8rem',
                              color: 'rgba(255, 255, 255, 0.5)',
                              textAlign: 'center',
                            }}
                          >
                            No recipients selected. Please select one or more employees from the <strong>Organization Directory</strong> panel on the right.
                          </div>
                        ) : (
                          <div
                            style={{
                              padding: '10px 12px',
                              borderRadius: '6px',
                              background: 'rgba(255, 255, 255, 0.03)',
                              border: '1px solid rgba(255, 255, 255, 0.08)',
                              display: 'flex',
                              flexWrap: 'wrap',
                              gap: '6px',
                              maxHeight: '120px',
                              overflowY: 'auto',
                            }}
                          >
                            {selectedEmployees.map((emp) => (
                              <span key={emp.id} className="saas-recipient-chip">
                                <span>{emp._name}</span>
                                <span style={{ opacity: 0.6 }}>&lt;{emp._email}&gt;</span>
                                <button
                                  type="button"
                                  className="saas-recipient-chip-remove"
                                  onClick={() => removeSelected(emp.id)}
                                  title={`Remove ${emp._name}`}
                                >
                                  <X size={12} />
                                </button>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Subject input */}
                      <div className="saas-input-group">
                        <label className="saas-label">Subject</label>
                        <input
                          type="text"
                          className="saas-input"
                          placeholder="e.g. Q4 Engineering Architecture Review Invitation"
                          value={sendSubject}
                          onChange={(e) => setSendSubject(e.target.value)}
                        />
                      </div>

                      {/* HTML Body input */}
                      <div className="saas-input-group">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                          <label className="saas-label" style={{ margin: 0 }}>HTML / Message Body</label>
                          <span style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.45)' }}>
                            HTML markup supported
                          </span>
                        </div>
                        <textarea
                          className="saas-textarea"
                          rows={8}
                          placeholder="<p>Dear Team,</p><p>Please join us for tomorrow's project review meeting...</p>"
                          value={sendHtmlBody}
                          onChange={(e) => setSendHtmlBody(e.target.value)}
                          style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.85rem' }}
                        />
                      </div>

                      {/* Live Email Preview Box */}
                      {sendSubject && sendHtmlBody && (
                        <div style={{ marginBottom: '20px' }}>
                          <label className="saas-label">Live Dispatch Preview</label>
                          <div className="saas-preview-box">
                            <div className="saas-preview-header-row">
                              <span className="saas-preview-header-label">From</span>
                              <span className="saas-preview-header-value">Organization Mailbox (via Gmail API)</span>
                            </div>
                            <div className="saas-preview-header-row">
                              <span className="saas-preview-header-label">To</span>
                              <span className="saas-preview-header-value">
                                {selectedEmployees.map((e) => `${e._name} <${e._email}>`).join(', ') || '(Select recipients)'}
                              </span>
                            </div>
                            <div className="saas-preview-header-row">
                              <span className="saas-preview-header-label">Subject</span>
                              <span className="saas-preview-header-value">{sendSubject}</span>
                            </div>
                            <div
                              className="saas-preview-body-content"
                              dangerouslySetInnerHTML={{ __html: sendHtmlBody }}
                            />
                          </div>
                        </div>
                      )}

                      {/* Action buttons */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <button
                          type="button"
                          className="saas-btn saas-btn-cyan"
                          disabled={!canSend}
                          onClick={handleInitiateSend}
                        >
                          {sendExec.isLoading ? (
                            <>
                              <Loader2 size={15} className="animate-spin" />
                              <span>Sending Email...</span>
                            </>
                          ) : (
                            <>
                              <Send size={15} />
                              <span>Preview & Send Email ({selectedEmployees.length} recipients)</span>
                            </>
                          )}
                        </button>

                        <button
                          type="button"
                          className="saas-btn saas-btn-secondary"
                          onClick={() => {
                            setSendSubject('');
                            setSendHtmlBody('');
                          }}
                        >
                          Clear
                        </button>
                      </div>

                      {/* Success confirmation result banner */}
                      {sendSuccessResult && (
                        <div
                          style={{
                            marginTop: '20px',
                            padding: '14px 18px',
                            borderRadius: '8px',
                            background: 'rgba(34, 197, 94, 0.1)',
                            border: '1px solid rgba(34, 197, 94, 0.3)',
                            color: '#86efac',
                            fontSize: '0.85rem',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, marginBottom: '4px' }}>
                            <CheckCircle2 size={18} color="#22c55e" />
                            <span>Email Dispatched Successfully</span>
                          </div>
                          <div style={{ fontSize: '0.78rem', color: 'rgba(255, 255, 255, 0.75)', lineHeight: 1.5 }}>
                            Dispatched to {sendSuccessResult.recipientCount} recipient(s) at {sendSuccessResult.timestamp}.
                            <br />
                            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.72rem' }}>
                              Idempotency: {sendSuccessResult.idempotencyKey}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Send Execution Result */}
                  <AgentExecutionResult
                    isLoading={sendExec.isLoading}
                    response={sendExec.response}
                    error={sendExec.error}
                    executionMeta={sendExec.executionMeta}
                  />
                </div>
              )}

              {/* ========================================================= */}
              {/* TAB 3: SCHEDULE MEETING WORKFLOW                          */}
              {/* ========================================================= */}
              {activeTab === 'meeting' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Meeting Form Card */}
                  <div className="saas-card">
                    <div className="saas-card-header">
                      <div className="saas-card-title">
                        <Calendar size={16} color="#4A9DC4" />
                        <span>Schedule AXON Meeting</span>
                      </div>
                      <span className="saas-badge-cyan">Backend Calendar API</span>
                    </div>

                    <div className="saas-card-body">
                      {/* Form grid */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {/* Title */}
                        <div className="saas-input-group" style={{ margin: 0 }}>
                          <label className="saas-label">Meeting Title *</label>
                          <input
                            type="text"
                            className="saas-input"
                            placeholder="e.g. Q4 Architecture Review & Infrastructure Sync"
                            value={meetingTitle}
                            onChange={(e) => setMeetingTitle(e.target.value)}
                          />
                        </div>

                        {/* Date & Time Row */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                          <div className="saas-input-group" style={{ margin: 0 }}>
                            <label className="saas-label" htmlFor="meeting-date">Meeting Date *</label>
                            <input
                              id="meeting-date"
                              type="date"
                              className="saas-input"
                              value={meetingDate}
                              onChange={(e) => setMeetingDate(e.target.value)}
                            />
                          </div>

                          <div className="saas-input-group" style={{ margin: 0 }}>
                            <label className="saas-label" htmlFor="meeting-start-time">Start Time *</label>
                            <input
                              id="meeting-start-time"
                              type="time"
                              className="saas-input"
                              value={meetingStartTime}
                              onChange={(e) => setMeetingStartTime(e.target.value)}
                            />
                          </div>

                          <div className="saas-input-group" style={{ margin: 0 }}>
                            <label className="saas-label" htmlFor="meeting-end-time">End Time *</label>
                            <input
                              id="meeting-end-time"
                              type="time"
                              className="saas-input"
                              value={meetingEndTime}
                              onChange={(e) => setMeetingEndTime(e.target.value)}
                            />
                          </div>
                        </div>

                        {/* Timezone & Venue Row */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                          <div className="saas-input-group" style={{ margin: 0 }}>
                            <label className="saas-label">Timezone</label>
                            <select
                              className="saas-input"
                              value={meetingTimezone}
                              onChange={(e) => setMeetingTimezone(e.target.value)}
                            >
                              {COMMON_TIMEZONES.map((tz) => (
                                <option key={tz} value={tz}>
                                  {tz}
                                </option>
                              ))}
                            </select>
                          </div>

                          <div className="saas-input-group" style={{ margin: 0 }}>
                            <label className="saas-label">Venue / Meeting URL (Optional)</label>
                            <input
                              type="text"
                              className="saas-input"
                              placeholder="e.g. Main Boardroom / https://meet.google.com/xyz"
                              value={meetingVenue}
                              onChange={(e) => setMeetingVenue(e.target.value)}
                            />
                          </div>
                        </div>

                        {/* Description / Agenda */}
                        <div className="saas-input-group" style={{ margin: 0 }}>
                          <label className="saas-label">Description / Agenda (Optional)</label>
                          <textarea
                            className="saas-textarea"
                            rows={3}
                            placeholder="Key goals, sync agenda, topics to cover..."
                            value={meetingDescription}
                            onChange={(e) => setMeetingDescription(e.target.value)}
                          />
                        </div>

                        {/* Attendees Display */}
                        <div>
                          <label className="saas-label">Attendees ({selectedEmployees.length} selected)</label>
                          {selectedEmployees.length === 0 ? (
                            <div
                              style={{
                                padding: '12px',
                                borderRadius: '6px',
                                background: 'rgba(255, 255, 255, 0.02)',
                                border: '1px dashed rgba(255, 255, 255, 0.15)',
                                fontSize: '0.78rem',
                                color: 'rgba(255, 255, 255, 0.5)',
                              }}
                            >
                              Please select at least one attendee from the <strong>Organization Directory</strong> panel on the right.
                            </div>
                          ) : (
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                              {selectedEmployees.map((emp) => (
                                <span key={emp.id} className="saas-recipient-chip">
                                  <span>{emp._name}</span>
                                  <span style={{ opacity: 0.6 }}>&lt;{emp._email}&gt;</span>
                                  <button
                                    type="button"
                                    className="saas-recipient-chip-remove"
                                    onClick={() => removeSelected(emp.id)}
                                  >
                                    <X size={12} />
                                  </button>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Error Alert */}
                        {meetingError && (
                          <div
                            style={{
                              padding: '12px 14px',
                              borderRadius: '6px',
                              background: 'rgba(239, 68, 68, 0.1)',
                              border: '1px solid rgba(239, 68, 68, 0.25)',
                              color: '#fca5a5',
                              fontSize: '0.8rem',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                            }}
                          >
                            <AlertCircle size={16} />
                            <span>{meetingError.message || 'Failed to schedule meeting.'}</span>
                          </div>
                        )}

                        {/* Submit Button */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '6px' }}>
                          <button
                            type="button"
                            className="saas-btn saas-btn-cyan"
                            disabled={!canSchedule}
                            onClick={handleCreateMeeting}
                          >
                            {meetingLoading ? (
                              <>
                                <Loader2 size={15} className="animate-spin" />
                                <span>Scheduling Meeting...</span>
                              </>
                            ) : (
                              <>
                                <Calendar size={15} />
                                <span>Create Scheduled Meeting</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Scheduled Meeting Success Card & Invitation Dispatch */}
                  {meetingResult && (
                    <div className="saas-card">
                      <div className="saas-card-header">
                        <div className="saas-card-title">
                          <CheckCircle2 size={16} color="#22c55e" />
                          <span>Meeting Scheduled: {meetingResult.title}</span>
                        </div>
                        <span className="saas-badge-emerald">Status: Scheduled</span>
                      </div>

                      <div className="saas-card-body">
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                            gap: '12px',
                            padding: '14px',
                            borderRadius: '8px',
                            background: 'rgba(255, 255, 255, 0.03)',
                            border: '1px solid rgba(255, 255, 255, 0.08)',
                            fontSize: '0.8rem',
                            marginBottom: '16px',
                          }}
                        >
                          <div>
                            <span style={{ color: 'rgba(255, 255, 255, 0.5)', display: 'block', fontSize: '0.72rem' }}>
                              MEETING ID
                            </span>
                            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem', color: '#e4e4e7' }}>
                              {meetingResult.id}
                            </span>
                          </div>
                          <div>
                            <span style={{ color: 'rgba(255, 255, 255, 0.5)', display: 'block', fontSize: '0.72rem' }}>
                              TIME & TIMEZONE
                            </span>
                            <span style={{ color: '#e4e4e7' }}>
                              {meetingDate} {meetingStartTime} - {meetingEndTime} ({meetingTimezone})
                            </span>
                          </div>
                          <div>
                            <span style={{ color: 'rgba(255, 255, 255, 0.5)', display: 'block', fontSize: '0.72rem' }}>
                              VENUE
                            </span>
                            <span style={{ color: '#e4e4e7' }}>
                              {meetingResult.venue || 'No venue specified'}
                            </span>
                          </div>
                        </div>

                        {/* Invitation Dispatch Section */}
                        <div
                          style={{
                            padding: '16px',
                            borderRadius: '8px',
                            background: 'rgba(74, 157, 196, 0.05)',
                            border: '1px solid rgba(74, 157, 196, 0.2)',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.85rem', color: '#e0f2fe' }}>
                              <Mail size={16} color="#4A9DC4" />
                              <span>Dispatch Calendar Invitations to Attendees</span>
                            </div>
                            <button
                              type="button"
                              className="saas-btn saas-btn-cyan"
                              style={{ padding: '6px 14px', fontSize: '0.78rem' }}
                              disabled={inviteLoading}
                              onClick={() => setShowInviteModal(true)}
                            >
                              {inviteLoading ? (
                                <>
                                  <Loader2 size={14} className="animate-spin" />
                                  <span>Dispatching...</span>
                                </>
                              ) : (
                                <>
                                  <Send size={14} />
                                  <span>Send Invitations</span>
                                </>
                              )}
                            </button>
                          </div>

                          <p style={{ fontSize: '0.78rem', color: 'rgba(255, 255, 255, 0.65)', margin: 0 }}>
                            Meeting record created. Click <strong>Send Invitations</strong> to email calendar invitation notifications to all registered attendee mailboxes with strict confirmation.
                          </p>

                          {inviteResult && (
                            <div
                              style={{
                                marginTop: '12px',
                                padding: '10px 14px',
                                borderRadius: '6px',
                                background: 'rgba(34, 197, 94, 0.1)',
                                border: '1px solid rgba(34, 197, 94, 0.25)',
                                color: '#86efac',
                                fontSize: '0.78rem',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                              }}
                            >
                              <CheckCircle2 size={15} />
                              <span>Invitations dispatched successfully to meeting attendees.</span>
                            </div>
                          )}

                          {inviteError && (
                            <div
                              style={{
                                marginTop: '12px',
                                padding: '10px 14px',
                                borderRadius: '6px',
                                background: 'rgba(239, 68, 68, 0.1)',
                                border: '1px solid rgba(239, 68, 68, 0.25)',
                                color: '#fca5a5',
                                fontSize: '0.78rem',
                              }}
                            >
                              {inviteError.message || 'Failed to dispatch invitations.'}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Recent Organization Meetings Table */}
                  <div className="saas-card">
                    <div className="saas-card-header">
                      <div className="saas-card-title">
                        <Clock size={16} color="#4A9DC4" />
                        <span>Recent Organization Meetings</span>
                      </div>
                      <button
                        type="button"
                        className="saas-btn saas-btn-secondary"
                        style={{ padding: '3px 8px', fontSize: '0.72rem' }}
                        onClick={loadRecentMeetings}
                        disabled={recentMeetingsLoading}
                      >
                        <RefreshCw size={12} className={recentMeetingsLoading ? 'animate-spin' : ''} />
                        <span>Refresh</span>
                      </button>
                    </div>

                    <div className="saas-card-body" style={{ padding: 0 }}>
                      {recentMeetingsLoading ? (
                        <div style={{ padding: '24px', textAlign: 'center', color: 'rgba(255, 255, 255, 0.45)', fontSize: '0.8rem' }}>
                          <Loader2 size={16} className="animate-spin" style={{ margin: '0 auto 8px' }} />
                          Loading meetings...
                        </div>
                      ) : recentMeetings.length === 0 ? (
                        <div style={{ padding: '24px', textAlign: 'center', color: 'rgba(255, 255, 255, 0.45)', fontSize: '0.8rem' }}>
                          No meetings scheduled yet for your organization.
                        </div>
                      ) : (
                        <table className="saas-table">
                          <thead>
                            <tr>
                              <th>Meeting Title</th>
                              <th>Date & Time</th>
                              <th>Status</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {recentMeetings.map((m) => (
                              <tr key={m.id}>
                                <td style={{ fontWeight: 500, color: '#f4f4f5' }}>{m.title}</td>
                                <td style={{ fontSize: '0.75rem', fontFamily: 'JetBrains Mono, monospace' }}>
                                  {m.starts_at ? new Date(m.starts_at).toLocaleString() : '—'}
                                </td>
                                <td>
                                  <span className={m.status === 'scheduled' ? 'saas-badge-emerald' : 'saas-badge-amber'}>
                                    {m.status}
                                  </span>
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="saas-btn saas-btn-secondary"
                                    style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                                    onClick={() => {
                                      setMeetingResult(m);
                                      setInviteSubject(`Invitation: ${m.title}`);
                                      setInviteBody(`<p>You are invited to <strong>${escapeHtml(m.title)}</strong>.</p>`);
                                      setShowInviteModal(true);
                                    }}
                                  >
                                    Send Invite
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* RIGHT COLUMN: ORGANIZATION EMPLOYEE DIRECTORY */}
            <aside>
              <div className="saas-card" style={{ position: 'sticky', top: '76px' }}>
                <div className="saas-card-header">
                  <div className="saas-card-title">
                    <Users size={16} color="#4A9DC4" />
                    <span>Organization Directory</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: 'rgba(255, 255, 255, 0.05)',
                        color: 'rgba(255, 255, 255, 0.6)',
                        fontFamily: 'JetBrains Mono, monospace',
                      }}
                    >
                      {normalizedEmployees.length}
                    </span>
                    <button
                      type="button"
                      className="saas-btn saas-btn-secondary"
                      style={{ padding: '4px', borderRadius: '4px' }}
                      onClick={refreshEmployees}
                      title="Refresh Directory"
                      disabled={employeesLoading}
                    >
                      <RefreshCw size={12} className={employeesLoading ? 'animate-spin' : ''} />
                    </button>
                  </div>
                </div>

                <div className="saas-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {/* Search bar */}
                  <div style={{ position: 'relative' }}>
                    <Search
                      size={14}
                      color="rgba(255, 255, 255, 0.4)"
                      style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }}
                    />
                    <input
                      type="text"
                      className="saas-input"
                      style={{ paddingLeft: '32px', fontSize: '0.8rem' }}
                      placeholder="Search name, email, or role..."
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>

                  {/* Role filter dropdown & Select actions */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <select
                      className="saas-input"
                      style={{ flex: 1, padding: '6px 10px', fontSize: '0.75rem' }}
                      value={roleFilter}
                      onChange={(e) => setRoleFilter(e.target.value)}
                    >
                      {roles.map((r) => (
                        <option key={r} value={r}>
                          {r === 'all' ? 'All Roles' : `Role: ${r}`}
                        </option>
                      ))}
                    </select>

                    <button
                      type="button"
                      className="saas-btn saas-btn-secondary"
                      style={{ padding: '6px 10px', fontSize: '0.72rem', whiteSpace: 'nowrap' }}
                      onClick={selectAllFiltered}
                      title="Select all visible employees"
                    >
                      Select All
                    </button>
                  </div>

                  {/* Selected count & clear tray */}
                  {selectedEmployees.length > 0 && (
                    <div
                      style={{
                        padding: '8px 10px',
                        borderRadius: '6px',
                        background: 'rgba(74, 157, 196, 0.08)',
                        border: '1px solid rgba(74, 157, 196, 0.25)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <span style={{ fontSize: '0.75rem', color: '#7ad0fa', fontWeight: 500 }}>
                        {selectedEmployees.length} employee{selectedEmployees.length === 1 ? '' : 's'} selected
                      </span>
                      <button
                        type="button"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: 'rgba(255, 255, 255, 0.5)',
                          fontSize: '0.72rem',
                          cursor: 'pointer',
                        }}
                        onClick={clearSelection}
                      >
                        Clear
                      </button>
                    </div>
                  )}

                  {/* Employee List Scroll Area */}
                  <div
                    style={{
                      maxHeight: '380px',
                      overflowY: 'auto',
                      borderRadius: '6px',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      background: 'rgba(0, 0, 0, 0.2)',
                    }}
                  >
                    {employeesLoading ? (
                      <div style={{ padding: '24px', textAlign: 'center', color: 'rgba(255, 255, 255, 0.45)', fontSize: '0.8rem' }}>
                        <Loader2 size={16} className="animate-spin" style={{ margin: '0 auto 8px' }} />
                        Loading employees...
                      </div>
                    ) : employeesError ? (
                      <div style={{ padding: '16px', color: '#fca5a5', fontSize: '0.78rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, marginBottom: '4px' }}>
                          <AlertCircle size={14} />
                          <span>Directory Unavailable</span>
                        </div>
                        <p style={{ margin: 0, opacity: 0.8 }}>
                          {employeesError.message || 'Could not load employees from organization.'}
                        </p>
                      </div>
                    ) : filteredEmployees.length === 0 ? (
                      <div style={{ padding: '20px', textAlign: 'center', color: 'rgba(255, 255, 255, 0.45)', fontSize: '0.78rem' }}>
                        No active employees match your criteria.
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        {filteredEmployees.map((emp) => {
                          const checked = selectedIds.includes(emp.id);
                          const initials = emp._name
                            .split(' ')
                            .map((p) => p[0])
                            .slice(0, 2)
                            .join('')
                            .toUpperCase() || 'EM';

                          return (
                            <label
                              key={emp.id}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px',
                                padding: '10px 12px',
                                borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                                cursor: 'pointer',
                                background: checked ? 'rgba(74, 157, 196, 0.08)' : 'transparent',
                                transition: 'background 0.15s ease',
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleEmployee(emp.id)}
                                style={{ accentColor: '#4A9DC4', cursor: 'pointer' }}
                              />

                              <div
                                style={{
                                  width: '26px',
                                  height: '26px',
                                  borderRadius: '50%',
                                  background: checked ? '#4A9DC4' : 'rgba(255, 255, 255, 0.08)',
                                  color: checked ? '#09090b' : '#fafafa',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  fontSize: '0.65rem',
                                  fontWeight: 600,
                                  flexShrink: 0,
                                }}
                              >
                                {initials}
                              </div>

                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '4px' }}>
                                  <span
                                    style={{
                                      fontSize: '0.8rem',
                                      fontWeight: 500,
                                      color: '#f4f4f5',
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {emp._name}
                                  </span>
                                  <span
                                    style={{
                                      fontSize: '0.62rem',
                                      padding: '1px 5px',
                                      borderRadius: '3px',
                                      background: 'rgba(255, 255, 255, 0.06)',
                                      color: 'rgba(255, 255, 255, 0.5)',
                                      fontFamily: 'JetBrains Mono, monospace',
                                      textTransform: 'uppercase',
                                    }}
                                  >
                                    {emp._role}
                                  </span>
                                </div>
                                <div
                                  style={{
                                    fontSize: '0.72rem',
                                    color: 'rgba(255, 255, 255, 0.45)',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                >
                                  {emp._email}
                                </div>
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.4)', lineHeight: 1.4 }}>
                    Sourced from registered users in your organization. UUIDs are verified strictly on backend dispatch.
                  </div>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </main>

      {/* ========================================================= */}
      {/* MODAL: EXPLICIT SEND EMAIL CONFIRMATION                   */}
      {/* ========================================================= */}
      {showSendConfirmModal && (
        <div className="saas-modal-backdrop" onClick={() => setShowSendConfirmModal(false)}>
          <div className="saas-modal" onClick={(e) => e.stopPropagation()}>
            <div className="saas-card-header">
              <div className="saas-card-title">
                <AlertCircle size={18} color="#f59e0b" />
                <span>Confirm Email Dispatch</span>
              </div>
              <button
                type="button"
                className="saas-recipient-chip-remove"
                onClick={() => setShowSendConfirmModal(false)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="saas-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <p style={{ margin: 0, fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.85)', lineHeight: 1.5 }}>
                You are about to dispatch real emails to <strong>{selectedEmployees.length} recipient(s)</strong> through the organization's verified Gmail mailbox.
              </p>

              <div
                style={{
                  padding: '12px',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  fontSize: '0.78rem',
                }}
              >
                <div style={{ marginBottom: '6px' }}>
                  <span style={{ color: 'rgba(255, 255, 255, 0.45)' }}>Subject: </span>
                  <span style={{ color: '#fff', fontWeight: 500 }}>{sendSubject}</span>
                </div>
                <div>
                  <span style={{ color: 'rgba(255, 255, 255, 0.45)' }}>Recipients: </span>
                  <span style={{ color: '#e0f2fe' }}>
                    {selectedEmployees.map((e) => e._email).join(', ')}
                  </span>
                </div>
              </div>

              <div style={{ fontSize: '0.75rem', color: '#fca5a5' }}>
                Note: This action is permanent, idempotent, and audited.
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  className="saas-btn saas-btn-secondary"
                  onClick={() => setShowSendConfirmModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="saas-btn saas-btn-cyan"
                  onClick={handleConfirmSendEmail}
                >
                  <Send size={14} />
                  <span>Yes, Confirm & Send Email</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* MODAL: EXPLICIT MEETING INVITATION CONFIRMATION           */}
      {/* ========================================================= */}
      {showInviteModal && meetingResult && (
        <div className="saas-modal-backdrop" onClick={() => setShowInviteModal(false)}>
          <div className="saas-modal" onClick={(e) => e.stopPropagation()}>
            <div className="saas-card-header">
              <div className="saas-card-title">
                <Send size={18} color="#4A9DC4" />
                <span>Confirm Invitation Dispatch</span>
              </div>
              <button
                type="button"
                className="saas-recipient-chip-remove"
                onClick={() => setShowInviteModal(false)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="saas-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="saas-input-group" style={{ margin: 0 }}>
                <label className="saas-label">Invitation Subject</label>
                <input
                  type="text"
                  className="saas-input"
                  value={inviteSubject}
                  onChange={(e) => setInviteSubject(e.target.value)}
                />
              </div>

              <div className="saas-input-group" style={{ margin: 0 }}>
                <label className="saas-label">Invitation Body (HTML)</label>
                <textarea
                  className="saas-textarea"
                  rows={6}
                  value={inviteBody}
                  onChange={(e) => setInviteBody(e.target.value)}
                  style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.8rem' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button
                  type="button"
                  className="saas-btn saas-btn-secondary"
                  onClick={() => setShowInviteModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="saas-btn saas-btn-cyan"
                  onClick={handleConfirmSendInvitation}
                >
                  <Send size={14} />
                  <span>Dispatch Invitations</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
