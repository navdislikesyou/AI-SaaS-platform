/**
 * Tests for the Performance dataset upload hooks.
 *
 * `performanceService` is mocked, so no network request is made and no dataset is
 * sent anywhere. These cover the states the page depends on: selected file,
 * in-flight upload, confirmed dataset, and a failure that must not be presented
 * as success.
 *
 * The extension list is asserted directly rather than through the backend,
 * because the point of listing `.csv` and `.xlsx` only is that `.xls` is refused
 * before a request is made instead of failing inside a job later.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../services/api';
import { performanceService } from '../services/performanceService';
import { useDatasetUpload } from './useDatasetUpload';
import { usePerformanceDatasets } from './usePerformanceDatasets';

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

function makeFile(name = 'Financials.csv', type = 'text/csv') {
  return new File(['date,sales\n2026-01-01,1000\n'], name, { type });
}

function readyDataset(overrides = {}) {
  return {
    dataset_id: 'ds-001',
    filename: 'Financials.csv',
    format: 'csv',
    size_bytes: 2048,
    status: 'ready',
    uploaded_at: '2026-10-17T10:00:00+00:00',
    column_names: ['date', 'sales'],
    column_count: 2,
    is_sample: false,
    available: true,
    ...overrides,
  };
}

function sampleDataset() {
  return readyDataset({
    dataset_id: 'sample',
    filename: 'Financials_standardized.csv',
    size_bytes: 301,
    column_names: [],
    column_count: 0,
    is_sample: true,
  });
}

function listing(datasets = [sampleDataset()]) {
  return {
    datasets,
    total: datasets.length,
    max_upload_bytes: 26214400,
    supported_extensions: ['.csv', '.xlsx'],
  };
}

beforeEach(() => {
  vi.mocked(performanceService.uploadDataset).mockReset();
  vi.mocked(performanceService.listDatasets).mockReset();
  vi.mocked(performanceService.listDatasets).mockResolvedValue(listing());
});

describe('useDatasetUpload', () => {
  it('starts with no file, no upload in flight, and no dataset', () => {
    const { result } = renderHook(() => useDatasetUpload());

    expect(result.current.selectedFile).toBeNull();
    expect(result.current.isUploading).toBe(false);
    expect(result.current.uploadedDataset).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.errorMessage).toBe('');
  });

  it('holds the selected file before anything is sent', () => {
    const { result } = renderHook(() => useDatasetUpload());
    const file = makeFile();

    act(() => result.current.selectFile(file));

    expect(result.current.selectedFile).toBe(file);
    expect(performanceService.uploadDataset).not.toHaveBeenCalled();
  });

  it('reports the dataset only after the backend confirms it', async () => {
    vi.mocked(performanceService.uploadDataset).mockResolvedValue({
      success: true,
      data: { dataset: readyDataset() },
    });

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.uploadedDataset).toMatchObject({ dataset_id: 'ds-001' });
    expect(result.current.error).toBeNull();
    expect(result.current.isUploading).toBe(false);
  });

  it('refuses a legacy .xls workbook before sending it', async () => {
    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile('Book1.xls', 'application/vnd.ms-excel')));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error.message).toMatch(/unsupported file type/i);
    expect(performanceService.uploadDataset).not.toHaveBeenCalled();
    expect(result.current.uploadedDataset).toBeNull();
  });

  it('accepts both csv and xlsx names', async () => {
    vi.mocked(performanceService.uploadDataset).mockResolvedValue({
      data: { dataset: readyDataset() },
    });

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile('Book1.xlsx', 'application/vnd.ms-excel')));
    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeNull();
    expect(performanceService.uploadDataset).toHaveBeenCalledTimes(1);
  });

  it('surfaces a backend rejection and does not claim a dataset was stored', async () => {
    vi.mocked(performanceService.uploadDataset).mockRejectedValue(
      new ApiError("'x.csv' is empty.", 422, 'VALIDATION_ERROR')
    );

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.errorMessage).toMatch(/is empty/i);
    expect(result.current.uploadedDataset).toBeNull();
    expect(result.current.isUploading).toBe(false);
  });

  it('reports an unreachable backend plainly', async () => {
    vi.mocked(performanceService.uploadDataset).mockRejectedValue(
      new ApiError('Network request failed.', 0, 'NETWORK_ERROR')
    );

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));
    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.errorMessage).toMatch(/could not reach the backend/i);
  });

  it('treats a 201 without a ready dataset as a failure', async () => {
    vi.mocked(performanceService.uploadDataset).mockResolvedValue({
      data: { dataset: readyDataset({ status: 'failed' }) },
    });

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));
    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.uploadedDataset).toBeNull();
  });

  it('exposes the in-flight state so the page can disable its controls', async () => {
    let release;
    vi.mocked(performanceService.uploadDataset).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ data: { dataset: readyDataset() } });
      })
    );

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));
    act(() => {
      result.current.upload();
    });

    await waitFor(() => expect(result.current.isUploading).toBe(true));

    await act(async () => {
      release();
    });
  });

  it('ignores a second upload while one is in flight', async () => {
    let release;
    vi.mocked(performanceService.uploadDataset).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ data: { dataset: readyDataset() } });
      })
    );

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));
    act(() => {
      result.current.upload();
    });

    await act(async () => {
      await result.current.upload();
    });

    expect(performanceService.uploadDataset).toHaveBeenCalledTimes(1);

    await act(async () => {
      release();
    });
  });

  it('clears a stale error when a new file is chosen', async () => {
    vi.mocked(performanceService.uploadDataset).mockRejectedValue(
      new ApiError('nope', 422, 'VALIDATION_ERROR')
    );

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));
    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).not.toBeNull();

    act(() => result.current.selectFile(makeFile('other.csv')));

    await waitFor(() => expect(result.current.error).toBeNull());
  });

  it('refuses a file past the server-reported limit before sending it', async () => {
    const { result } = renderHook(() => useDatasetUpload({ maxBytes: 8 }));

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error.message).toMatch(/too large/i);
    expect(performanceService.uploadDataset).not.toHaveBeenCalled();
    expect(result.current.uploadedDataset).toBeNull();
  });

  it('sends a file within the server-reported limit', async () => {
    vi.mocked(performanceService.uploadDataset).mockResolvedValue({
      data: { dataset: readyDataset() },
    });

    const { result } = renderHook(() => useDatasetUpload({ maxBytes: 1024 * 1024 }));

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeNull();
    expect(performanceService.uploadDataset).toHaveBeenCalledTimes(1);
  });

  it('does not guess a limit when the server has not reported one', async () => {
    vi.mocked(performanceService.uploadDataset).mockResolvedValue({
      data: { dataset: readyDataset() },
    });

    const { result } = renderHook(() => useDatasetUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeNull();
    expect(performanceService.uploadDataset).toHaveBeenCalledTimes(1);
  });
});

describe('usePerformanceDatasets', () => {
  it('loads the available datasets and the server limits', async () => {
    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.datasets).toHaveLength(1);
    expect(result.current.datasets[0].dataset_id).toBe('sample');
    expect(result.current.maxUploadBytes).toBe(26214400);
    expect(result.current.supportedExtensions).toEqual(['.csv', '.xlsx']);
  });

  it('offers the packaged sample even when nothing is uploaded', async () => {
    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.datasets).toHaveLength(1));

    expect(result.current.datasets[0].is_sample).toBe(true);
  });

  it('keeps an unusable dataset out of the selectable list', async () => {
    vi.mocked(performanceService.listDatasets).mockResolvedValue(
      listing([sampleDataset(), readyDataset({ dataset_id: 'ds-bad', status: 'failed' })])
    );

    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.datasets.map((row) => row.dataset_id)).toEqual(['sample']);
    expect(result.current.failedDatasets).toHaveLength(1);
  });

  it('keeps an unavailable dataset out of the selectable list', async () => {
    vi.mocked(performanceService.listDatasets).mockResolvedValue(
      listing([sampleDataset(), readyDataset({ dataset_id: 'ds-gone', available: false })])
    );

    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.datasets.map((row) => row.dataset_id)).toEqual(['sample']);
  });

  it('reports a listing failure without throwing', async () => {
    vi.mocked(performanceService.listDatasets).mockRejectedValue(
      new ApiError('Could not reach the backend.', 0, 'NETWORK_ERROR')
    );

    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.error).not.toBeNull());

    expect(result.current.datasets).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it('adds an uploaded dataset without refetching, keeping the sample first', async () => {
    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.addDataset(readyDataset()));

    expect(result.current.datasets.map((row) => row.dataset_id)).toEqual(['sample', 'ds-001']);
    expect(performanceService.listDatasets).toHaveBeenCalledTimes(1);
  });

  it('replaces rather than duplicates an existing entry', async () => {
    vi.mocked(performanceService.listDatasets).mockResolvedValue(
      listing([sampleDataset(), readyDataset()])
    );

    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.datasets).toHaveLength(2));

    act(() => result.current.addDataset(readyDataset({ column_count: 9 })));

    expect(result.current.datasets).toHaveLength(2);
    expect(result.current.datasets[1].column_count).toBe(9);
  });

  it('ignores an entry with no identifier', async () => {
    const { result } = renderHook(() => usePerformanceDatasets());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.addDataset({ filename: 'broken.csv' }));

    expect(result.current.datasets).toHaveLength(1);
  });
});