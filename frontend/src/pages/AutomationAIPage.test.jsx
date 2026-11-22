import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AutomationAIPage from './AutomationAIPage';
import { AuthProvider } from '../context/AuthContext';
import { agentService } from '../services/agentService';
import { apiClient } from '../services/api';

vi.mock('../services/authService', () => ({
  authService: {
    login: vi.fn(),
    logout: vi.fn(),
    fetchCurrentUser: vi.fn(),
    hydrateSession: vi.fn(() =>
      Promise.resolve({
        id: 'usr-admin-1',
        name: 'Admin User',
        email: 'admin@axon.ai',
        role: 'admin',
        organizationId: 'org-test-1',
      })
    ),
    toSessionUser: (profile) => profile,
  },
}));

vi.mock('../services/agentService', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    agentService: {
      ...actual.agentService,
      getAgents: vi.fn().mockResolvedValue([
        { id: 'automation', isBackend: true, available: true, name: 'automation' },
      ]),
      executeAgent: vi.fn(),
    },
  };
});

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      get: vi.fn(),
      post: vi.fn(),
    },
  };
});

const MOCK_EMPLOYEES = [
  { id: 'emp-001', full_name: 'Aarti Rao', email: 'aarti@example.com', role: 'manager' },
  { id: 'emp-002', full_name: 'Omkar Shenwai', email: 'omkar@example.com', role: 'employee' },
  { id: 'emp-003', full_name: 'Marcus Vance', email: 'marcus@example.com', role: 'admin' },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <AutomationAIPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiClient.get).mockImplementation(async (endpoint) => {
    if (endpoint === '/automation/employees') {
      return { data: MOCK_EMPLOYEES };
    }
    if (endpoint.startsWith('/meetings')) {
      return { data: { meetings: [] } };
    }
    return { data: {} };
  });

  vi.mocked(agentService.executeAgent).mockResolvedValue({
    success: true,
    data: {
      agent: 'automation',
      operation: 'draft_action',
      duration_ms: 45,
      data: {
        meeting: {
          title: 'Architecture Review',
          date: 'Tomorrow',
          time: '10:00 AM',
          venue: 'Virtual',
          attendees: ['Aarti Rao'],
        },
        recipients: [{ name: 'Aarti Rao', email: 'aarti@example.com' }],
        email: 'Dear Aarti,\n\nPlease join us for the architecture review tomorrow at 10 AM.',
        employee_count: 3,
      },
    },
    request_id: 'req-draft-1',
  });
});

describe('AutomationAIPage Layout & Structure', () => {
  it('renders within the saas-workbench frame with main container', async () => {
    const { container } = renderPage();
    expect(container.querySelector('.saas-workbench')).toBeInTheDocument();
    expect(container.querySelector('.saas-main-container')).toBeInTheDocument();
    expect(screen.getByText('Task Automation Agent')).toBeInTheDocument();
  });

  it('renders all three workflow tabs: Draft Email, Send Email, and Schedule Meeting', async () => {
    renderPage();
    expect(screen.getByRole('button', { name: /Draft Email/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Send Email/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Schedule Meeting/i })).toBeInTheDocument();
  });

  it('renders the Organization Directory panel with active employees', async () => {
    renderPage();
    expect(await screen.findByText('Organization Directory')).toBeInTheDocument();
    expect(await screen.findByText('Aarti Rao')).toBeInTheDocument();
    expect(screen.getByText('Omkar Shenwai')).toBeInTheDocument();
    expect(screen.getByText('Marcus Vance')).toBeInTheDocument();
  });
});

describe('Workflow A: Draft Email', () => {
  it('allows typing an instruction and triggers draft_action', async () => {
    const user = userEvent.setup();
    renderPage();

    const textarea = screen.getByPlaceholderText(/e\.g\. Draft an email inviting/i);
    await user.type(textarea, 'Draft a sprint planning email for the team');

    const draftBtn = screen.getByRole('button', { name: /Generate Draft Action/i });
    expect(draftBtn).toBeEnabled();
    await user.click(draftBtn);

    await waitFor(() => {
      expect(agentService.executeAgent).toHaveBeenCalledWith('automation', 'draft_action', {
        instruction: 'Draft a sprint planning email for the team',
      });
    });

    expect(await screen.findByText('Generated Draft Preview')).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Please join us for the architecture review/i)).toBeInTheDocument();
  });

  it('transfers the generated draft into the Send Email workflow', async () => {
    const user = userEvent.setup();
    renderPage();

    const textarea = screen.getByPlaceholderText(/e\.g\. Draft an email inviting/i);
    await user.type(textarea, 'Draft team sync');
    await user.click(screen.getByRole('button', { name: /Generate Draft Action/i }));

    const transferBtn = await screen.findByRole('button', { name: /Transfer to Send Email/i });
    await user.click(transferBtn);

    // Should switch to Send Email tab and pre-populate fields
    expect(screen.getByText('Verified Email Dispatch')).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Please join us for the architecture review/i)).toBeInTheDocument();
  });
});

describe('Workflow B: Send Email', () => {
  it('requires selecting recipients before sending and opens confirmation modal', async () => {
    const user = userEvent.setup();
    renderPage();

    // Switch to Send Email tab
    await user.click(screen.getByRole('button', { name: /Send Email/i }));
    expect(screen.getByText('Verified Email Dispatch')).toBeInTheDocument();
    expect(screen.getByText(/No recipients selected/i)).toBeInTheDocument();

    // Select Aarti Rao from the organization directory
    const aartiCheckbox = screen.getByLabelText(/Aarti Rao/i);
    await user.click(aartiCheckbox);

    // Fill in subject and body
    const subjectInput = screen.getByPlaceholderText(/e\.g\. Q4 Engineering/i);
    await user.type(subjectInput, 'Architecture Decision Record');

    const bodyInput = screen.getByPlaceholderText(/<p>Dear Team,<\/p>/i);
    await user.type(bodyInput, '<p>Architecture proposal is ready.</p>');

    // Click Send
    const sendBtn = screen.getByRole('button', { name: /Preview & Send Email/i });
    expect(sendBtn).toBeEnabled();
    await user.click(sendBtn);

    // Confirm modal should appear
    expect(await screen.findByText('Confirm Email Dispatch')).toBeInTheDocument();
    const modal = document.querySelector('.saas-modal');
    expect(within(modal).getByText('aarti@example.com')).toBeInTheDocument();

    // Mock send response
    vi.mocked(agentService.executeAgent).mockResolvedValueOnce({
      success: true,
      data: {
        agent: 'automation',
        operation: 'send_email',
        duration_ms: 120,
        data: { message_id: 'msg-999', status: 'sent' },
      },
    });

    const confirmBtn = screen.getByRole('button', { name: /Yes, Confirm & Send Email/i });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(agentService.executeAgent).toHaveBeenCalledWith(
        'automation',
        'send_email',
        expect.objectContaining({
          employee_ids: ['emp-001'],
          subject: 'Architecture Decision Record',
          html_body: '<p>Architecture proposal is ready.</p>',
          confirm: true,
        })
      );
    });

    expect(await screen.findByText('Email Dispatched Successfully')).toBeInTheDocument();
  });
});

describe('Workflow C: Schedule Meeting', () => {
  it('validates required fields and calls meeting API', async () => {
    const user = userEvent.setup();
    renderPage();

    // Switch to Schedule Meeting tab
    await user.click(screen.getByRole('button', { name: /Schedule Meeting/i }));
    expect(screen.getByText('Schedule AXON Meeting')).toBeInTheDocument();

    // Select an employee as attendee
    const aartiCheckbox = screen.getByLabelText(/Aarti Rao/i);
    await user.click(aartiCheckbox);

    // Fill in meeting details
    const titleInput = screen.getByPlaceholderText(/e\.g\. Q4 Architecture Review/i);
    await user.type(titleInput, 'Sprint 24 Planning');

    const dateInput = screen.getByLabelText(/Meeting Date/i);
    await user.type(dateInput, '2026-12-01');

    const startTimeInput = screen.getByLabelText(/Start Time/i);
    await user.type(startTimeInput, '10:00');

    const endTimeInput = screen.getByLabelText(/End Time/i);
    await user.type(endTimeInput, '11:00');

    // Mock meeting creation
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: {
        id: 'meet-123',
        title: 'Sprint 24 Planning',
        starts_at: '2026-12-01T10:00:00Z',
        ends_at: '2026-12-01T11:00:00Z',
        timezone: 'UTC',
        status: 'scheduled',
      },
    });

    const createBtn = screen.getByRole('button', { name: /Create Scheduled Meeting/i });
    expect(createBtn).toBeEnabled();
    await user.click(createBtn);

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        '/meetings',
        expect.objectContaining({
          title: 'Sprint 24 Planning',
          attendees: expect.arrayContaining([
            expect.objectContaining({
              user_id: 'emp-001',
              name: 'Aarti Rao',
              email: 'aarti@example.com',
            }),
          ]),
        })
      );
    });

    expect(await screen.findByText('Meeting Scheduled: Sprint 24 Planning')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Send Invitations/i })).toBeInTheDocument();
  });
});
