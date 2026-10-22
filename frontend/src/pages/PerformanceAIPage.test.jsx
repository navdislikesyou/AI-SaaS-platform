/**
 * Tests for the Performance dataset selection and upload workflow.
 *
 * `performanceService` is mocked, so nothing is uploaded and no job runs against
 * pandas. What these verify is the part that is easy to get wrong: that a job is
 * submitted with a dataset id rather than a path, that the selection a user
 * sees is the selection the job reads, and that an operation the user picked
 * still dispatches unchanged.
 */

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PerformanceAIPage from './PerformanceAIPage';
import { AuthProvider } from '../context/AuthContext';
import { ApiError } from '../services/api';
import { performanceService } from '../services/performanceService';

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

vi.mock('../services/performanceService', async (importOriginal) => {
  const actual = await importOriginal();

  return {
    ...actual,
    performanceService: {
      fetchArtifact: vi.fn(),
      createJob: vi.fn(),
      getJob: vi.fn(),
      uploadDataset: vi.fn(),
      listDatasets: vi.fn(),
    },
  };
});

const CSV_FILE = new File(['date,sales,profit\n2026-01-01,1000,200\n'], 'Financials.csv', {
  type: 'text/csv',
});

function sampleDataset() {
  return {
    dataset_id: 'sample',
    filename: 'Financials_standardized.csv',
    format: 'csv',
    size_bytes: 301,
    status: 'ready',
    uploaded_at: '2026-10-17T09:00:00+00:00',
    column_names: [],
    column_count: 0,
    is_sample: true,
    available: true,
  };
}

function uploadedDataset(overrides = {}) {
  return {
    dataset_id: 'ds-001',
    filename: 'Financials.csv',
    format: 'csv',
    size_bytes: 2048,
    status: 'ready',
    uploaded_at: '2026-10-17T10:00:00+00:00',
    column_names: ['date', 'sales', 'profit'],
    column_count: 3,
    is_sample: false,
    available: true,
    ...overrides,
  };
}

function listing(datasets) {
  return {
    datasets,
    total: datasets.length,
    max_upload_bytes: 26214400,
    supported_extensions: ['.csv', '.xlsx'],
  };
}

function createdJob(overrides = {}) {
  return {
    job_id: 'job-1',
    status: 'queued',
    operation: 'compute_kpis',
    created_at: '2026-10-17T10:00:00+00:00',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <PerformanceAIPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(performanceService.listDatasets).mockReset();
  vi.mocked(performanceService.listDatasets).mockResolvedValue(listing([sampleDataset()]));
  vi.mocked(performanceService.createJob).mockReset();
  vi.mocked(performanceService.createJob).mockResolvedValue(createdJob());
  vi.mocked(performanceService.getJob).mockReset();
  vi.mocked(performanceService.getJob).mockResolvedValue({
    ...createdJob(),
    status: 'completed',
    result: { overall: { total_sales: 2500 } },
    started_at: '2026-10-17T10:00:01+00:00',
    completed_at: '2026-10-17T10:00:02+00:00',
  });
  vi.mocked(performanceService.uploadDataset).mockReset();
  vi.mocked(performanceService.fetchArtifact).mockReset();
  vi.mocked(performanceService.fetchArtifact).mockResolvedValue(
    new Blob(['png-bytes'], { type: 'image/png' })
  );
  window.localStorage.clear();
});


/**
 * Wait for the dataset picker to be populated, then return it.
 *
 * The listing arrives asynchronously, so the select exists before its options
 * do. Selecting from an empty select fails for reasons that have nothing to
 * do with the behaviour under test.
 *
 * @returns {Promise<HTMLElement>} The populated select.
 */
async function findDatasetSelect() {
  const select = await screen.findByLabelText('Dataset to Analyse');
  await screen.findByRole('option', { name: /Financials\.csv/ });
  return select;
}

describe('PerformanceAIPage dataset selection', () => {
  it('selects the packaged sample before anything is uploaded', async () => {
    renderPage();

    const select = await screen.findByLabelText('Dataset to Analyse');

    expect(select).toHaveValue('sample');
    expect(await screen.findByText(/packaged sample dataset/i)).toBeInTheDocument();
  });

  it('offers every dataset the backend reports', async () => {
    vi.mocked(performanceService.listDatasets).mockResolvedValue(
      listing([sampleDataset(), uploadedDataset()])
    );

    renderPage();

    const select = await findDatasetSelect();
    const labels = Array.from(select.options).map((option) => option.textContent);

    expect(labels.join(' ')).toContain('Sample dataset');
    expect(labels.join(' ')).toContain('Financials.csv');
  });

  it('names the dataset that will be analysed', async () => {
    vi.mocked(performanceService.listDatasets).mockResolvedValue(
      listing([sampleDataset(), uploadedDataset()])
    );

    const user = userEvent.setup();

    renderPage();

    const select = await findDatasetSelect();
    await user.selectOptions(select, 'ds-001');

    expect(await screen.findByText(/Analysing Financials\.csv/i)).toBeInTheDocument();
  });
});

describe('PerformanceAIPage dataset upload', () => {
  it('offers a file control limited to CSV and XLSX', async () => {
    renderPage();

    const input = await screen.findByLabelText('Upload Dataset');

    expect(input).toHaveAttribute('accept', '.csv,.xlsx');
  });

  it('states the server limit and accepted formats', async () => {
    renderPage();

    const input = await screen.findByLabelText('Upload Dataset');

    // Scoped to the upload control's own group, and awaited, because the limit
    // arrives with the dataset listing rather than on first render.
    const group = input.closest('.saas-input-group');

    expect(await within(group).findByText(/\.csv, \.xlsx/)).toBeInTheDocument();
    expect(within(group).getByText(/25\.0 MB/)).toBeInTheDocument();
  });

  it('shows the chosen file and its size before uploading', async () => {
    const user = userEvent.setup();

    renderPage();

    await user.upload(await screen.findByLabelText('Upload Dataset'), CSV_FILE);

    expect(screen.getByText('Financials.csv')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload Dataset/i })).toBeEnabled();
  });

  it('disables the upload button until a file is chosen', async () => {
    renderPage();

    const button = await screen.findByRole('button', { name: /Upload Dataset/i });

    await waitFor(() => expect(button).toBeDisabled());
  });

  it('shows a loading state while the dataset is being stored', async () => {
    const user = userEvent.setup();
    let release;
    vi.mocked(performanceService.uploadDataset).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ data: { dataset: uploadedDataset() } });
      })
    );

    renderPage();

    await user.upload(await screen.findByLabelText('Upload Dataset'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Dataset/i }));

    expect(await screen.findByText(/Validating and storing/i)).toBeInTheDocument();

    await act(async () => {
      release();
    });
  });

  it('confirms success only after the backend stored the dataset', async () => {
    const user = userEvent.setup();
    vi.mocked(performanceService.uploadDataset).mockResolvedValue({
      success: true,
      data: { dataset: uploadedDataset() },
    });

    renderPage();

    await user.upload(await screen.findByLabelText('Upload Dataset'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Dataset/i }));

    expect(
      await screen.findByText(/Stored .*Financials\.csv.* with 3 columns/i)
    ).toBeInTheDocument();
  });

  it('selects a freshly uploaded dataset so the next run uses it', async () => {
    const user = userEvent.setup();
    vi.mocked(performanceService.uploadDataset).mockResolvedValue({
      data: { dataset: uploadedDataset() },
    });

    renderPage();

    await user.upload(await screen.findByLabelText('Upload Dataset'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Dataset/i }));

    await waitFor(() =>
      expect(screen.getByLabelText('Dataset to Analyse')).toHaveValue('ds-001')
    );

    expect(performanceService.listDatasets).toHaveBeenCalledTimes(1);
  });

  it('surfaces a backend rejection and claims no dataset was stored', async () => {
    const user = userEvent.setup();
    vi.mocked(performanceService.uploadDataset).mockRejectedValue(
      new ApiError("'Financials.csv' is empty.", 422, 'VALIDATION_ERROR')
    );

    renderPage();

    await user.upload(await screen.findByLabelText('Upload Dataset'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Dataset/i }));

    const alert = await screen.findByRole('alert');

    expect(alert).toHaveTextContent(/is empty/i);
    expect(screen.queryByText(/Stored .*Financials\.csv/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText('Dataset to Analyse')).toHaveValue('sample');
  });

  it('refuses a legacy .xls file without sending it', async () => {
    const user = userEvent.setup();

    renderPage();

    // fireEvent rather than userEvent: the picker's own accept attribute would
    // filter this file out before the guard under test ever saw it. The point is
    // that the upload path refuses it too, not that the picker hides it.
    fireEvent.change(await screen.findByLabelText('Upload Dataset'), {
      target: {
        files: [
          new File(['binary'], 'Book1.xls', { type: 'application/vnd.ms-excel' }),
        ],
      },
    });

    await user.click(screen.getByRole('button', { name: /Upload Dataset/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/unsupported file type/i);
    expect(performanceService.uploadDataset).not.toHaveBeenCalled();
  });

  it('reports an unreachable backend plainly', async () => {
    const user = userEvent.setup();
    vi.mocked(performanceService.uploadDataset).mockRejectedValue(
      new ApiError('Network request failed.', 0, 'NETWORK_ERROR')
    );

    renderPage();

    await user.upload(await screen.findByLabelText('Upload Dataset'), CSV_FILE);
    await user.click(screen.getByRole('button', { name: /Upload Dataset/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the backend/i);
  });

  it('keeps the upload control available when the listing fails', async () => {
    vi.mocked(performanceService.listDatasets).mockRejectedValue(
      new ApiError('Could not reach the backend.', 0, 'NETWORK_ERROR')
    );

    renderPage();

    expect(await screen.findByText(/Could not load the dataset list/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Upload Dataset')).toBeInTheDocument();
  });
});

describe('PerformanceAIPage job submission', () => {
  it('submits a dataset id and never a filesystem path', async () => {
    const user = userEvent.setup();
    vi.mocked(performanceService.listDatasets).mockResolvedValue(
      listing([sampleDataset(), uploadedDataset()])
    );

    renderPage();

    await user.selectOptions(await findDatasetSelect(), 'ds-001');
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    await waitFor(() => expect(performanceService.createJob).toHaveBeenCalledTimes(1));

    const [operation, filePath, datasetId] =
      vi.mocked(performanceService.createJob).mock.calls[0];

    expect(operation).toBe('compute_kpis');
    expect(datasetId).toBe('ds-001');
    expect(filePath).toBeUndefined();
  });

  it('submits the packaged sample id by default', async () => {
    const user = userEvent.setup();

    renderPage();

    await screen.findByLabelText('Dataset to Analyse');
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    await waitFor(() => expect(performanceService.createJob).toHaveBeenCalledTimes(1));

    expect(vi.mocked(performanceService.createJob).mock.calls[0][2]).toBe('sample');
  });

  it('sends only the dataset id in the request body', async () => {
    const user = userEvent.setup();

    renderPage();

    await screen.findByLabelText('Dataset to Analyse');
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    await waitFor(() => expect(performanceService.createJob).toHaveBeenCalledTimes(1));

    const [, filePath] = vi.mocked(performanceService.createJob).mock.calls[0];

    expect(filePath).toBeUndefined();
  });

  it('keeps the operation the user selected', async () => {
    const user = userEvent.setup();

    renderPage();

    await screen.findByLabelText('Dataset to Analyse');
    await user.click(screen.getByRole('button', { name: /Compare Periods/i }));
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    await waitFor(() => expect(performanceService.createJob).toHaveBeenCalledTimes(1));

    expect(vi.mocked(performanceService.createJob).mock.calls[0][0]).toBe('compare_periods');
  });

  it('renders the job result for the completed operation', async () => {
    const user = userEvent.setup();

    renderPage();

    await screen.findByLabelText('Dataset to Analyse');
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    expect(await screen.findByText(/Assistant Response Ready/i)).toBeInTheDocument();
  });

  it('does not present a failed job as a completed one', async () => {
    const user = userEvent.setup();
    vi.mocked(performanceService.getJob).mockResolvedValue({
      ...createdJob(),
      status: 'failed',
      error: 'TimeAnalyzer requires column(s): [date]',
    });

    renderPage();

    await screen.findByLabelText('Dataset to Analyse');
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    expect(await screen.findByText(/requires column/i)).toBeInTheDocument();
  });
});

describe('PerformanceAIPage chart preview', () => {
  it('shows the chart that was opened', async () => {
    const user = userEvent.setup();

    vi.mocked(performanceService.createJob).mockResolvedValue(
      createdJob({
        job_id: 'job-viz',
        operation: 'visualize',
        status: 'completed',
        result: {
          generated: 2,
          visualizations: [
            { name: 'channel_profit', filename: 'channel_profit.png', size_bytes: 23853 },
            { name: 'channel_sales', filename: 'channel_sales.png', size_bytes: 24404 },
          ],
        },
      })
    );

    vi.mocked(performanceService.fetchArtifact).mockResolvedValue(
      new Blob(['png-bytes'], { type: 'image/png' })
    );

    renderPage();

    await screen.findByLabelText('Dataset to Analyse');
    await user.click(screen.getByRole('button', { name: /^Charts$/i }));
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    // The chart list appears once the job reports what it generated.
    await screen.findByText(/GENERATED CHARTS/i);

    await user.click(screen.getByText('channel_profit.png'));

    // The chart is fetched through the authenticated client, not pointed at
    // with a plain image URL, and it renders from an object URL.
    await waitFor(() =>
      expect(performanceService.fetchArtifact).toHaveBeenCalledWith(
        'job-viz',
        'channel_profit.png'
      )
    );

    const image = await screen.findByAltText('channel_profit chart');

    expect(image).toHaveAttribute('src', expect.stringContaining('blob:'));
    expect(screen.queryByText(/Unable to load/i)).not.toBeInTheDocument();
  });

  it('explains a chart that cannot be loaded instead of showing a broken image', async () => {
    const user = userEvent.setup();

    vi.mocked(performanceService.createJob).mockResolvedValue(
      createdJob({
        job_id: 'job-viz',
        operation: 'visualize',
        status: 'completed',
        result: {
          generated: 1,
          visualizations: [
            { name: 'channel_profit', filename: 'channel_profit.png', size_bytes: 23853 },
          ],
        },
      })
    );

    vi.mocked(performanceService.fetchArtifact).mockRejectedValue(
      new ApiError("Artifact 'channel_profit.png' was not found.", 404, 'JOB_NOT_FOUND')
    );

    renderPage();

    await screen.findByLabelText('Dataset to Analyse');
    await user.click(screen.getByRole('button', { name: /^Charts$/i }));
    await user.click(screen.getByRole('button', { name: /Run Analysis/i }));

    await screen.findByText(/GENERATED CHARTS/i);

    await user.click(screen.getByText('channel_profit.png'));

    expect(await screen.findByText(/no longer available/i)).toBeInTheDocument();
    expect(screen.queryByAltText('channel_profit chart')).not.toBeInTheDocument();
  });
});

describe('PerformanceAIPage dataset format guidance', () => {
  it('describes the browser upload workflow rather than a server path', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /Dataset Source/i }));

    // The section now tells the user to upload from their device.
    expect(
      await screen.findByText(/Upload a dataset from this device/i)
    ).toBeInTheDocument();

    const box = screen.getByText('Dataset format').closest('.saas-info-box');

    expect(box).toHaveTextContent(/\.csv.*\.xlsx/i);
    expect(box).toHaveTextContent(/\.xls workbooks are refused/i);
    expect(box).toHaveTextContent(/kept on the server this page is talking to/i);

    // The old instruction to place files on the backend is gone, including the
    // server-side path field it referred to.
    expect(box).not.toHaveTextContent(/must already exist on disk/i);
    expect(box).not.toHaveTextContent(/server-side path/i);
    expect(screen.queryByLabelText(/File Path/i)).not.toBeInTheDocument();
  });

  it('keeps the schema guidance and the column-count interaction', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /Dataset Source/i }));

    const box = (await screen.findByText('Dataset format')).closest('.saas-info-box');

    expect(box.querySelectorAll('.saas-info-req').length).toBeGreaterThan(0);
    expect(box.querySelectorAll('.saas-info-opt').length).toBeGreaterThan(0);

    expect(box).toHaveTextContent(/sales_channel/);
    expect(box).toHaveTextContent(/Columns are not uniform across operations/i);
    expect(box).toHaveTextContent(/employee_name.*sales_target/s);
  });

  it('keeps the example header row collapsed until asked for', async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(screen.getByRole('button', { name: /Dataset Source/i }));

    const toggle = await screen.findByRole('button', { name: /Example header row/i });

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/Financials\.csv — header only/)).not.toBeInTheDocument();

    await user.click(toggle);

    expect(screen.getByText(/Financials\.csv — header only/)).toBeInTheDocument();
  });

  it('lists the available datasets on this server', async () => {
    vi.mocked(performanceService.listDatasets).mockResolvedValue(
      listing([sampleDataset(), uploadedDataset()])
    );

    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /Dataset Source/i }));

    const table = await screen.findByRole('table');

    expect(within(table).getByText('Financials.csv')).toBeInTheDocument();
    expect(within(table).getByText('Packaged sample')).toBeInTheDocument();
    expect(within(table).getByText('Uploaded')).toBeInTheDocument();
  });
});