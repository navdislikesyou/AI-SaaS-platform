/**
 * Tests for the employee directory UI on the Automation page.
 *
 * The Automation service and the agent execution service are mocked, so these
 * tests exercise the page's own state handling — upload, preview, selection, and
 * the payload it sends — without a backend or a network call.
 *
 * The payload assertions matter most. A directory selector that never reaches
 * the backend would look correct and silently draft against the default roster.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AutomationAIPage from './AutomationAIPage';
import { AuthProvider } from '../context/AuthContext';
import { ApiError } from '../services/api';
import { agentService } from '../services/agentService';
import { automationService } from '../services/automationService';

vi.mock('../services/authService', () => ({
  authService: {
    login: vi.fn(),
    logout: vi.fn(),
    fetchCurrentUser: vi.fn(),
    // The session is restored on mount. There is none here, so the page
    // renders for a signed-out visitor, exactly as an expired cookie would.
    hydrateSession: vi.fn(() => Promise.resolve(null)),
    toSessionUser: (profile) => profile,
  },
}));

vi.mock('../services/automationService', async (importOriginal) => {
  const actual = await importOriginal();

  return {
    ...actual,
    automationService: {
      uploadDirectory: vi.fn(),
      listDirectories: vi.fn(),
      getDirectory: vi.fn(),
    },
  };
});

vi.mock('../services/agentService', async (importOriginal) => {
  const actual = await importOriginal();

  return {
    ...actual,
    agentService: {
      ...actual.agentService,
      executeAgent: vi.fn(),
    },
  };
});

const CSV_FILE = new File(['name,email\nAarti Rao,aarti@example.com\n'], 'engineering.csv', {
  type: 'text/csv',
});

function readyDirectory(overrides = {}) {
  return {
    directory_id: 'dir-001',
    filename: 'engineering.csv',
    format: 'csv',
    employee_count: 2,
    size_bytes: 128,
    status: 'ready',
    uploaded_at: '2026-10-16T14:22:01+00:00',
    ...overrides,
  };
}

const PREVIEW = [
  { name: 'Aarti Rao', email: 'aarti@example.com' },
  { name: 'Omkar Shenwai', email: 'omkar@example.com' },
];

function draftResponse(overrides = {}) {
  return {
    success: true,
    data: {
      agent: 'automation',
      operation: 'draft_action',
      duration_ms: 12,
      data: {
        meeting: {
          title: 'Sprint Planning',
          date: '5 March',
          time: '10 AM',
          venue: 'Conference Room A',
          attendees: ['Aarti Rao'],
        },
        recipients: [{ name: 'Aarti Rao', email: 'aarti@example.com' }],
        email: 'Dear Team,\n\nSprint planning is scheduled for 5 March.',
        directory: { directory_id: null, source: 'default', employee_count: 4 },
        ...overrides,
      },
    },
    request_id: 'req-1',
  };
}

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
  vi.mocked(automationService.uploadDirectory).mockReset();
  vi.mocked(automationService.listDirectories).mockReset();
  vi.mocked(automationService.listDirectories).mockResolvedValue([]);
  vi.mocked(agentService.executeAgent).mockReset();
  vi.mocked(agentService.executeAgent).mockResolvedValue(draftResponse());
  window.localStorage.clear();
});

describe('AutomationAIPage employee directory', () => {
  it('offers the upload control and a default directory option', async () => {
    renderPage();

    expect(await screen.findByLabelText('Directory File')).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: /Default employee directory/i })
    ).toBeInTheDocument();
  });

  it('restricts the picker to JSON and CSV', async () => {
    renderPage();

    const input = await screen.findByLabelText('Directory File');

    expect(input).toHaveAttribute('accept', '.json,.csv');
  });

  it('disables the upload button until a file is chosen', async () => {
    renderPage();

    const button = screen.getByRole('button', { name: /Upload Directory/i });

    await waitFor(() => expect(button).toBeDisabled());
  });

  it('shows the selected filename before uploading', async () => {
    const user = userEvent.setup();

    renderPage();

    const input = await screen.findByLabelText('Directory File');
    await user.upload(input, CSV_FILE);

    expect(screen.getByText('engineering.csv')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload Directory/i })).toBeEnabled();
  });

  it('previews the uploaded records and reports the accepted count', async () => {
    const user = userEvent.setup();

    vi.mocked(automationService.uploadDirectory).mockResolvedValue({
      data: { directory: readyDirectory(), preview: PREVIEW },
    });

    renderPage();

    await user.upload(await screen.findByLabelText('Directory File'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Directory/i }));

    expect(await screen.findByText('Aarti Rao')).toBeInTheDocument();
    expect(screen.getByText('aarti@example.com')).toBeInTheDocument();
    expect(screen.getByText('Omkar Shenwai')).toBeInTheDocument();
    expect(screen.getByText(/Accepted .* with 2 employees/i)).toBeInTheDocument();
  });

  it('makes the uploaded directory selectable without a refetch', async () => {
    const user = userEvent.setup();

    vi.mocked(automationService.uploadDirectory).mockResolvedValue({
      data: { directory: readyDirectory(), preview: PREVIEW },
    });

    renderPage();

    await user.upload(await screen.findByLabelText('Directory File'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Directory/i }));

    await waitFor(() =>
      expect(screen.getByRole('option', { name: /engineering\.csv/i })).toBeInTheDocument()
    );

    expect(automationService.listDirectories).toHaveBeenCalledTimes(1);
  });

  it('surfaces a backend rejection and claims no success', async () => {
    const user = userEvent.setup();

    vi.mocked(automationService.uploadDirectory).mockRejectedValue(
      new ApiError("Entry 2 in 'engineering.csv' repeats the 'name' of entry 1.", 422, 'VALIDATION_ERROR')
    );

    renderPage();

    await user.upload(await screen.findByLabelText('Directory File'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Directory/i }));

    const alert = await screen.findByRole('alert');

    expect(alert).toHaveTextContent(/repeats the 'name' of entry 1/);
    expect(screen.queryByText(/Accepted .* with 2 employees/i)).not.toBeInTheDocument();
  });

  it('reports an unreachable backend plainly', async () => {
    const user = userEvent.setup();

    vi.mocked(automationService.uploadDirectory).mockRejectedValue(
      new ApiError('Network request failed.', 0, 'NETWORK_ERROR')
    );

    renderPage();

    await user.upload(await screen.findByLabelText('Directory File'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Directory/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the backend/i);
  });

  it('warns about a rejected directory without hiding the upload control', async () => {
    vi.mocked(automationService.listDirectories).mockResolvedValue([
      readyDirectory({ directory_id: 'dir-002', status: 'failed' }),
    ]);

    renderPage();

    expect(await screen.findByText(/rejected and cannot be selected/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Directory File')).toBeInTheDocument();
  });
});

describe('AutomationAIPage employee directory guidance', () => {
  it('states the accepted formats and rejects spreadsheets implicitly', async () => {
    renderPage();

    const box = (await screen.findByText('Employee directory format')).closest(
      '.saas-info-box'
    );

    expect(box).toHaveTextContent(/\.csv/);
    expect(box).toHaveTextContent(/\.json/);
    expect(box).toHaveTextContent(/not enough/i);
  });

  it('marks name and email as required and gives the file limits', async () => {
    renderPage();

    const box = (await screen.findByText('Employee directory format')).closest(
      '.saas-info-box'
    );

    expect(box.querySelectorAll('.saas-info-req').length).toBeGreaterThan(0);
    expect(box).toHaveTextContent(/Each\s*name/i);
    expect(box).toHaveTextContent(/without regard to case/i);
    expect(box).toHaveTextContent(/rejects the whole file/i);
    expect(box).toHaveTextContent(/5,000/);
    expect(box).toHaveTextContent(/2\s*MB/);
  });

  it('describes the limits of name matching rather than overstating it', async () => {
    renderPage();

    const box = (await screen.findByText('Employee directory format')).closest(
      '.saas-info-box'
    );

    expect(box).toHaveTextContent(/full name/i);
    expect(box).toHaveTextContent(/first name only/i);
    expect(box).toHaveTextContent(/surname on its own resolves to nobody/i);
    expect(box).toHaveTextContent(/no matching by nickname, initials, or team/i);
  });

  it('repeats that a directory produces a draft and nothing else', async () => {
    renderPage();

    const box = (await screen.findByText('Employee directory format')).closest(
      '.saas-info-box'
    );

    expect(box).toHaveTextContent(/Nothing is sent and nothing is scheduled/i);
  });

  it('keeps the CSV example collapsed until asked for', async () => {
    const user = userEvent.setup();

    renderPage();

    const toggle = await screen.findByRole('button', { name: /CSV example/i });

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/Aarti Rao,aarti@example\.com/)).not.toBeInTheDocument();

    await user.click(toggle);

    expect(screen.getByText(/Aarti Rao,aarti@example\.com/)).toBeInTheDocument();
  });

  it('keeps the JSON example collapsed until asked for', async () => {
    const user = userEvent.setup();

    renderPage();

    const toggle = await screen.findByRole('button', { name: /JSON example/i });

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/engineering\.json/)).not.toBeInTheDocument();

    await user.click(toggle);

    expect(screen.getByText(/engineering\.json/)).toBeInTheDocument();
  });

  it('leaves the two examples independent', async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(await screen.findByRole('button', { name: /CSV example/i }));

    expect(screen.getByRole('button', { name: /JSON example/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('places the guidance next to the directory upload control', async () => {
    renderPage();

    const card = (await screen.findByLabelText('Directory File')).closest('.saas-card');

    expect(card).toContainElement(screen.getByText('Employee directory format'));
  });
});

describe('AutomationAIPage directory selection', () => {
  /**
   * Wait for the directory picker to be populated, then choose one.
   *
   * The listing arrives asynchronously, so the select exists before its
   * options do. Selecting from an empty select fails for reasons that have
   * nothing to do with the behaviour under test.
   *
   * @param {object} user The user-event driver.
   * @param {string} value The directory id to choose.
   */
  async function selectDirectory(user, value) {
    const select = await screen.findByLabelText('Employee Directory');
    await waitFor(() => expect(select.options.length).toBeGreaterThan(0));
    await user.selectOptions(select, value);
  }

  it('omits directory_id from the payload when the default is selected', async () => {
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByRole('textbox'), 'Draft a standup with Navneet');
    await user.click(screen.getByRole('button', { name: /Generate Draft/i }));

    await waitFor(() => expect(agentService.executeAgent).toHaveBeenCalledTimes(1));

    const [agent, operation, payload] = vi.mocked(agentService.executeAgent).mock.calls[0];

    expect(agent).toBe('automation');
    expect(operation).toBe('draft_action');
    expect(payload).toEqual({ instruction: 'Draft a standup with Navneet' });
    expect(payload).not.toHaveProperty('directory_id');
  });

  it('sends the selected directory_id in the payload', async () => {
    const user = userEvent.setup();

    vi.mocked(automationService.listDirectories).mockResolvedValue([readyDirectory()]);

    renderPage();

    await selectDirectory(user, 'dir-001');
    await user.type(screen.getByRole('textbox'), 'Draft a standup with Aarti');
    await user.click(screen.getByRole('button', { name: /Generate Draft/i }));

    await waitFor(() => expect(agentService.executeAgent).toHaveBeenCalledTimes(1));

    expect(vi.mocked(agentService.executeAgent).mock.calls[0][2]).toEqual({
      instruction: 'Draft a standup with Aarti',
      directory_id: 'dir-001',
    });
  });

  it('reports which directory produced the draft', async () => {
    const user = userEvent.setup();

    vi.mocked(agentService.executeAgent).mockResolvedValue(
      draftResponse({
        directory: { directory_id: 'dir-001', source: 'uploaded', employee_count: 2 },
      })
    );

    renderPage();

    await user.type(screen.getByRole('textbox'), 'Draft a standup with Aarti');
    await user.click(screen.getByRole('button', { name: /Generate Draft/i }));

    expect(await screen.findByText(/DIRECTORY USED/i)).toBeInTheDocument();
  });

  it('shows the default directory was used when nothing is selected', async () => {
    const user = userEvent.setup();

    renderPage();

    await user.type(screen.getByRole('textbox'), 'Draft a standup with Navneet');
    await user.click(screen.getByRole('button', { name: /Generate Draft/i }));

    const label = await screen.findByText(/DIRECTORY USED/i);

    expect(label).toHaveTextContent(/Default employee directory/i);
  });

  it('does not present a failed request as a completed one', async () => {
    const user = userEvent.setup();

    vi.mocked(agentService.executeAgent).mockRejectedValue(
      new ApiError('Agent execution failed.', 502, 'AGENT_EXECUTION_FAILED')
    );

    renderPage();

    await user.type(screen.getByRole('textbox'), 'Draft a standup with Navneet');
    await user.click(screen.getByRole('button', { name: /Generate Draft/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/Agent execution failed/);
    expect(screen.queryByText(/Assistant Response Ready/i)).not.toBeInTheDocument();
  });

  it('keeps the draft-only promise visible alongside the directory controls', async () => {
    renderPage();

    expect(screen.getByText(/Drafting only/i)).toBeInTheDocument();
  });
});