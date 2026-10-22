/**
 * Tests for the upload UI on the Knowledge page.
 *
 * The Knowledge service, the agent catalog, and the activity history are all
 * mocked, so these tests exercise the page's own state handling — selected file,
 * loading, success, and error rendering — without a backend or a network call.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import KnowledgeAIPage from './KnowledgeAIPage';
import { AuthProvider } from '../context/AuthContext';
import { ApiError } from '../services/api';
import { knowledgeService } from '../services/knowledgeService';

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

vi.mock('../services/knowledgeService', async (importOriginal) => {
  const actual = await importOriginal();

  return {
    ...actual,
    knowledgeService: {
      uploadDocument: vi.fn(),
      listDocuments: vi.fn(),
    },
  };
});

vi.mock('../hooks/useAgents', () => ({
  useAgents: () => ({
    agents: [{ id: 'knowledge', capabilities: ['query', 'ingest_document'] }],
    isLoading: false,
    error: null,
  }),
}));

vi.mock('../services/activityService', () => ({
  activityService: {
    getActivityHistory: vi.fn().mockResolvedValue([]),
    getRecentActivity: vi.fn().mockResolvedValue([]),
  },
}));

const PDF_FILE = new File(['%PDF-1.7 content'], 'Employee Handbook.pdf', {
  type: 'application/pdf',
});

function indexedDocument(overrides = {}) {
  return {
    document_id: 'doc-001',
    filename: 'Employee Handbook.pdf',
    extension: '.pdf',
    size_bytes: 2048,
    status: 'indexed',
    chunk_count: 7,
    uploaded_at: '2026-10-13T14:22:01+00:00',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <KnowledgeAIPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(knowledgeService.uploadDocument).mockReset();
  vi.mocked(knowledgeService.listDocuments).mockReset();
  vi.mocked(knowledgeService.listDocuments).mockResolvedValue([]);
  window.localStorage.clear();
});

describe('KnowledgeAIPage upload tab', () => {
  it('opens on the ingest tab with the upload control visible', async () => {
    renderPage();

    expect(await screen.findByLabelText('Document File')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload Document/i })).toBeInTheDocument();
  });

  it('restricts the picker to the accepted document types', async () => {
    renderPage();

    const input = await screen.findByLabelText('Document File');

    expect(input).toHaveAttribute('accept', '.pdf,.docx,.txt');
  });

  it('disables the upload button until a file is chosen', async () => {
    renderPage();

    const button = screen.getByRole('button', { name: /Upload Document/i });

    await waitFor(() => expect(button).toBeDisabled());
  });

  it('shows the selected filename before uploading', async () => {
    const user = userEvent.setup();

    renderPage();

    const input = await screen.findByLabelText('Document File');
    await user.upload(input, PDF_FILE);

    expect(screen.getByText('Employee Handbook.pdf')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload Document/i })).toBeEnabled();
  });

  it('shows a loading state while indexing and disables the button', async () => {
    const user = userEvent.setup();
    let release;
    vi.mocked(knowledgeService.uploadDocument).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ success: true, data: { document: indexedDocument() } });
      })
    );

    renderPage();

    const input = await screen.findByLabelText('Document File');
    await user.upload(input, PDF_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Document/i }));

    const status = await screen.findByText(/Uploading and indexing/i);

    expect(status).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Uploading & Indexing/i })).toBeDisabled();

    release();
  });

  it('confirms success only after the backend reports the document indexed', async () => {
    const user = userEvent.setup();
    vi.mocked(knowledgeService.uploadDocument).mockResolvedValue({
      success: true,
      data: { document: indexedDocument() },
    });

    renderPage();

    const input = await screen.findByLabelText('Document File');
    await user.upload(input, PDF_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Document/i }));

    expect(await screen.findByText(/Indexed .*Employee Handbook\.pdf.* as 7 chunks/i))
      .toBeInTheDocument();
  });

  it('shows the backend error message and no success message on failure', async () => {
    const user = userEvent.setup();
    vi.mocked(knowledgeService.uploadDocument).mockRejectedValue(
      new ApiError(
        "'Employee Handbook.pdf' is not a readable PDF.",
        422,
        'VALIDATION_ERROR'
      )
    );

    renderPage();

    const input = await screen.findByLabelText('Document File');
    await user.upload(input, PDF_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Document/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /not a readable PDF/i
    );
    expect(screen.queryByText(/Indexed .* as \d+ chunk/i)).not.toBeInTheDocument();
  });

  it('reports an unreachable backend in terms the user can act on', async () => {
    const user = userEvent.setup();
    vi.mocked(knowledgeService.uploadDocument).mockRejectedValue(
      new ApiError('Network request failed', 0, 'NETWORK_ERROR')
    );

    renderPage();

    const input = await screen.findByLabelText('Document File');
    await user.upload(input, PDF_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Document/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/Could not reach the backend/i);
  });

  it('clears a stale error when a different file is chosen', async () => {
    const user = userEvent.setup();
    vi.mocked(knowledgeService.uploadDocument).mockRejectedValue(
      new ApiError('Indexing failed.', 502, 'AGENT_EXECUTION_FAILED')
    );

    renderPage();

    const input = await screen.findByLabelText('Document File');
    await user.upload(input, PDF_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Document/i }));

    await screen.findByRole('alert');

    await user.upload(
      input,
      new File(['other'], 'Policy.pdf', { type: 'application/pdf' })
    );

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});

describe('KnowledgeAIPage file format guidance', () => {
  it('states the accepted formats and the size limit', async () => {
    renderPage();

    const box = (await screen.findByText('Preparing your document')).closest(
      '.saas-info-box'
    );

    expect(box).toHaveTextContent(/\.pdf/);
    expect(box).toHaveTextContent(/\.docx/);
    expect(box).toHaveTextContent(/\.txt/);
    expect(box).toHaveTextContent(/25\s*MB/);
  });

  it('separates what is required from what is only recommended', async () => {
    renderPage();

    const box = (await screen.findByText('Preparing your document')).closest(
      '.saas-info-box'
    );

    expect(box.querySelectorAll('.saas-info-req').length).toBeGreaterThan(0);
    expect(box.querySelectorAll('.saas-info-opt').length).toBeGreaterThan(0);

    // The readability rule and the 25 MB cap are requirements; headings and
    // tables are advice. Asserting on the copy keeps the two from being
    // silently swapped.
    expect(box).toHaveTextContent(/no OCR step/i);
    expect(box).toHaveTextContent(/do not guarantee a better answer/i);
    expect(box).toHaveTextContent(/row by row/i);
  });

  it('does not claim a citation verifies the answer', async () => {
    renderPage();

    const box = (await screen.findByText('Preparing your document')).closest(
      '.saas-info-box'
    );

    expect(box).toHaveTextContent(/They do not verify the answer/i);
  });

  it('keeps the example structure collapsed until asked for', async () => {
    const user = userEvent.setup();

    renderPage();

    const toggle = await screen.findByRole('button', {
      name: /Example structure/i,
    });

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/Employee Leave Policy/)).not.toBeInTheDocument();

    await user.click(toggle);

    expect(screen.getByText(/Employee Leave Policy/)).toBeInTheDocument();
    expect(screen.getByText(/Handbook\.docx/)).toBeInTheDocument();
  });

  it('presents the example as a recommendation, not a template', async () => {
    renderPage();

    expect(screen.getByRole('button', { name: /Example structure/i })).toHaveTextContent(
      /recommended, not required/i
    );
  });

  it('places the guidance inside the document ingestion card', async () => {
    renderPage();

    const card = (await screen.findByLabelText('Document File')).closest('.saas-card');

    expect(card).toContainElement(screen.getByText('Preparing your document'));
  });
});

describe('KnowledgeAIPage document selector', () => {
  it('offers an already indexed document for questioning', async () => {
    const user = userEvent.setup();

    vi.mocked(knowledgeService.listDocuments).mockResolvedValue([indexedDocument()]);

    renderPage();

    await user.click(screen.getByRole('button', { name: /Ask a Question/i }));

    const select = await screen.findByRole('combobox');

    expect(select).toHaveValue('');
    await user.selectOptions(select, 'doc-001');
    expect(select).toHaveValue('doc-001');
  });

  it('does not offer a document that failed to index', async () => {
    const user = userEvent.setup();

    vi.mocked(knowledgeService.listDocuments).mockResolvedValue([
      indexedDocument({ document_id: 'ok-1' }),
      indexedDocument({
        document_id: 'bad-1',
        filename: 'Scan.pdf',
        status: 'failed',
        chunk_count: null,
      }),
    ]);

    renderPage();

    await user.click(screen.getByRole('button', { name: /Ask a Question/i }));

    const select = await screen.findByRole('combobox');
    const labels = Array.from(select.options).map((option) => option.textContent);

    expect(labels.join(' ')).toContain('Employee Handbook.pdf');
    expect(labels.join(' ')).not.toContain('Scan.pdf');
  });

  it('prompts for an upload when nothing is indexed', async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(screen.getByRole('button', { name: /Ask a Question/i }));

    expect(await screen.findByText(/No documents ingested yet/i)).toBeInTheDocument();
  });
});