import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import InsightsAIPage from './InsightsAIPage';
import { agentService } from '../services/agentService';

vi.mock('../components/Navigation', () => ({
  default: () => <nav>AXON sidebar</nav>,
}));

vi.mock('../services/agentService', async (importOriginal) => {
  const actual = await importOriginal();

  return {
    ...actual,
    agentService: {
      ...actual.agentService,
      executeAgent: vi.fn(),
      getEmployeeFeedback: vi.fn(),
    },
  };
});

const EMAIL_TEXT =
  'Jon Clerk did an excellent job completing the client onboarding process.';

const FEEDBACK_RECORD = {
  id: 'feedback-1',
  employee_name: 'Jon Clerk',
  employee_email: 'jon.clerk@example.com',
  feedback: EMAIL_TEXT,
  sentiment: 'POSITIVE',
  confidence: 0.9584,
  created_at: '2026-10-31T12:00:00+00:00',
  saved: true,
  duplicate: false,
};

function historyResponse(records, page = 1, totalPages = 1, totalRecords = records.length) {
  return {
    success: true,
    data: {
      records,
      pagination: {
        page,
        page_size: 100,
        total_records: totalRecords,
        total_pages: totalPages,
      },
    },
  };
}

function apiResponse(records = [FEEDBACK_RECORD]) {
  return {
    success: true,
    data: {
      agent: 'employee_insights',
      operation: 'extract_feedback',
      data: {
        records,
        count: records.length,
        organization_id: 'a7d8b718-0c47-4a3b-9b43-c47f0a2ddaa1',
      },
    },
    message: 'Operation completed.',
    request_id: 'request-1',
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/agents/insights']}>
      <InsightsAIPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(agentService.executeAgent).mockReset();
  vi.mocked(agentService.getEmployeeFeedback)
    .mockReset()
    .mockResolvedValue(historyResponse([]));
});

describe('Employee Insights feedback analysis', () => {
  it('submits the exact payload without submitting a form and shows loading', async () => {
    vi.mocked(agentService.getEmployeeFeedback)
      .mockResolvedValueOnce(historyResponse([]))
      .mockResolvedValue(historyResponse([FEEDBACK_RECORD]));
    let resolveRequest;
    vi.mocked(agentService.executeAgent).mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve;
      })
    );

    renderPage();
    const user = userEvent.setup();
    const textarea = screen.getByPlaceholderText(/Paste email content/i);
    await user.type(textarea, EMAIL_TEXT);

    const button = screen.getByRole('button', { name: /Analyze Feedback/i });
    expect(button).toHaveAttribute('type', 'button');
    expect(button.closest('form')).toBeNull();

    await user.click(button);

    expect(agentService.executeAgent).toHaveBeenCalledWith(
      'employee_insights',
      'extract_feedback',
      { email_text: EMAIL_TEXT }
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Analyzing feedback');

    resolveRequest(apiResponse());
    expect(await screen.findByText('Jon Clerk')).toBeInTheDocument();
  });

  it('renders actual records, totals, sentiment counts, email and confidence', async () => {
    vi.mocked(agentService.getEmployeeFeedback)
      .mockResolvedValueOnce(historyResponse([]))
      .mockResolvedValue(historyResponse([FEEDBACK_RECORD]));
    vi.mocked(agentService.executeAgent).mockResolvedValue(apiResponse());

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Paste email content/i), EMAIL_TEXT);
    await user.click(screen.getByRole('button', { name: /Analyze Feedback/i }));

    expect(await screen.findByText('Analysis complete. 1 feedback record found.')).toBeInTheDocument();
    expect(screen.getByText('Total Feedback')).toBeInTheDocument();
    expect(screen.getByText('Positive')).toBeInTheDocument();
    expect(screen.getByText('Negative')).toBeInTheDocument();
    expect(screen.getByText('Neutral')).toBeInTheDocument();
    expect(screen.getByText('Jon Clerk')).toBeInTheDocument();
    expect(screen.getByText('jon.clerk@example.com')).toBeInTheDocument();
    expect(screen.getByText(EMAIL_TEXT)).toBeInTheDocument();
    expect(screen.getByText('POSITIVE')).toBeInTheDocument();
    expect(screen.getByText(/Confidence: 0\.9584/)).toBeInTheDocument();
    expect(screen.getByText('31 Oct 2026 · 05:30 PM')).toBeInTheDocument();
    expect(screen.getByText('Total Feedback').closest('.saas-card')).toHaveTextContent('1');
    expect(screen.getByText('Positive').closest('.saas-card')).toHaveTextContent('1');
  });

  it('shows an empty state when the backend returns no records', async () => {
    vi.mocked(agentService.executeAgent).mockResolvedValue(apiResponse([]));

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Paste email content/i), EMAIL_TEXT);
    await user.click(screen.getByRole('button', { name: /Analyze Feedback/i }));

    expect(
      await screen.findByText('No employee feedback records were found in this text.')
    ).toBeInTheDocument();
    expect(screen.getByText('Analysis complete. 0 feedback records found.')).toBeInTheDocument();
    expect(screen.getByText('Total Feedback').closest('.saas-card')).toHaveTextContent('0');
    expect(screen.getByText('Positive').closest('.saas-card')).toHaveTextContent('0');
    expect(screen.getByText('Negative').closest('.saas-card')).toHaveTextContent('0');
    expect(screen.getByText('Neutral').closest('.saas-card')).toHaveTextContent('0');
  });

  it('shows actual analysis values and preserves input when saving is unconfirmed', async () => {
    const unsavedRecord = { ...FEEDBACK_RECORD, saved: false, duplicate: false };
    vi.mocked(agentService.executeAgent).mockResolvedValue(apiResponse([unsavedRecord]));

    renderPage();
    const user = userEvent.setup();
    const textarea = screen.getByPlaceholderText(/Paste email content/i);
    await user.type(textarea, EMAIL_TEXT);
    await user.click(screen.getByRole('button', { name: /Analyze Feedback/i }));

    expect(await screen.findByText('Analysis results not saved')).toBeInTheDocument();
    expect(screen.getAllByText(EMAIL_TEXT)).toHaveLength(2);
    expect(screen.getByText(/POSITIVE · Confidence: 0\.9584/)).toBeInTheDocument();
    expect(textarea).toHaveValue(EMAIL_TEXT);
  });

  it('loads every history page and counts only saved backend records', async () => {
    const negativeRecord = {
      ...FEEDBACK_RECORD,
      id: 'feedback-2',
      employee_name: 'Avery Smith',
      feedback: 'Avery Smith missed the project deadline.',
      sentiment: 'NEGATIVE',
      confidence: 0.8123,
      created_at: '2026-10-30T12:00:00+00:00',
    };
    vi.mocked(agentService.getEmployeeFeedback)
      .mockResolvedValueOnce(historyResponse([FEEDBACK_RECORD], 1, 2, 2))
      .mockResolvedValueOnce(historyResponse([negativeRecord], 2, 2, 2));

    renderPage();

    expect(await screen.findByText('Saved Employee Feedback')).toBeInTheDocument();
    expect(screen.getByText('Total Feedback').closest('.saas-card')).toHaveTextContent('2');
    expect(screen.getByText('Positive').closest('.saas-card')).toHaveTextContent('1');
    expect(screen.getByText('Negative').closest('.saas-card')).toHaveTextContent('1');
    expect(screen.getByText('Neutral').closest('.saas-card')).toHaveTextContent('0');
    expect(screen.getByText('Avery Smith')).toBeInTheDocument();
    expect(agentService.getEmployeeFeedback).toHaveBeenNthCalledWith(1, 1, 100);
    expect(agentService.getEmployeeFeedback).toHaveBeenNthCalledWith(2, 2, 100);
  });

  it('shows a response error rather than rendering malformed analysis data', async () => {
    vi.mocked(agentService.executeAgent).mockResolvedValue({
      success: true,
      data: {
        agent: 'employee_insights',
        operation: 'extract_feedback',
        data: { records: null },
      },
    });

    renderPage();
    const user = userEvent.setup();
    const textarea = screen.getByPlaceholderText(/Paste email content/i);
    await user.type(textarea, EMAIL_TEXT);
    await user.click(screen.getByRole('button', { name: /Analyze Feedback/i }));

    expect(
      await screen.findByText('The analysis response did not contain feedback records.')
    ).toBeInTheDocument();
    expect(textarea).toHaveValue(EMAIL_TEXT);
  });

  it('preserves the input and shows an error when the request fails', async () => {
    vi.mocked(agentService.executeAgent).mockRejectedValue(new Error('Backend unavailable'));

    renderPage();
    const user = userEvent.setup();
    const textarea = screen.getByPlaceholderText(/Paste email content/i);
    await user.type(textarea, EMAIL_TEXT);
    await user.click(screen.getByRole('button', { name: /Analyze Feedback/i }));

    expect(await screen.findByText('Backend unavailable')).toBeInTheDocument();
    expect(textarea).toHaveValue(EMAIL_TEXT);
  });
});
