/**
 * Tests for the Automation employee directory hooks.
 *
 * `automationService` is mocked, so no network request is made and no employee
 * file is sent anywhere. These tests cover the states the page depends on:
 * selected file, in-flight upload, confirmed directory, and a failure that must
 * not be presented as success.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../services/api';
import { automationService } from '../services/automationService';
import { useDirectoryUpload } from './useDirectoryUpload';
import { useEmployeeDirectories } from './useEmployeeDirectories';

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

function makeFile(name = 'roster.csv', type = 'text/csv') {
  return new File(['name,email\nAarti Rao,a@example.com\n'], name, { type });
}

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

beforeEach(() => {
  vi.mocked(automationService.uploadDirectory).mockReset();
  vi.mocked(automationService.listDirectories).mockReset();
  vi.mocked(automationService.listDirectories).mockResolvedValue([]);
});

describe('useDirectoryUpload', () => {
  it('starts with no file, no upload in flight, and no directory', () => {
    const { result } = renderHook(() => useDirectoryUpload());

    expect(result.current.selectedFile).toBeNull();
    expect(result.current.isUploading).toBe(false);
    expect(result.current.uploadedDirectory).toBeNull();
    expect(result.current.preview).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('holds the selected file before anything is sent', () => {
    const { result } = renderHook(() => useDirectoryUpload());
    const file = makeFile();

    act(() => result.current.selectFile(file));

    expect(result.current.selectedFile).toBe(file);
    expect(automationService.uploadDirectory).not.toHaveBeenCalled();
  });

  it('reports the directory only after the backend confirms it', async () => {
    vi.mocked(automationService.uploadDirectory).mockResolvedValue({
      success: true,
      data: { directory: readyDirectory(), preview: PREVIEW },
    });

    const { result } = renderHook(() => useDirectoryUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.uploadedDirectory).toMatchObject({ directory_id: 'dir-001' });
    expect(result.current.preview).toEqual(PREVIEW);
    expect(result.current.error).toBeNull();
    expect(result.current.isUploading).toBe(false);
  });

  it('refuses a file type the backend would reject', async () => {
    const { result } = renderHook(() => useDirectoryUpload());

    act(() => result.current.selectFile(makeFile('roster.xlsx', 'application/vnd.ms-excel')));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error.message).toMatch(/unsupported file type/i);
    expect(automationService.uploadDirectory).not.toHaveBeenCalled();
    expect(result.current.uploadedDirectory).toBeNull();
  });

  it('accepts both JSON and CSV names', async () => {
    vi.mocked(automationService.uploadDirectory).mockResolvedValue({
      data: { directory: readyDirectory(), preview: PREVIEW },
    });

    const { result } = renderHook(() => useDirectoryUpload());

    act(() => result.current.selectFile(makeFile('roster.json', 'application/json')));
    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeNull();
    expect(automationService.uploadDirectory).toHaveBeenCalledTimes(1);
  });

  it('surfaces a backend rejection and does not claim a directory was accepted', async () => {
    vi.mocked(automationService.uploadDirectory).mockRejectedValue(
      new ApiError("Entry 2 in 'x.csv' repeats the 'name' of entry 1.", 422, 'VALIDATION_ERROR')
    );

    const { result } = renderHook(() => useDirectoryUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error.message).toMatch(/repeats the 'name' of entry 1/);
    expect(result.current.uploadedDirectory).toBeNull();
    expect(result.current.isUploading).toBe(false);
  });

  it('treats a 201 without a ready directory as a failure', async () => {
    vi.mocked(automationService.uploadDirectory).mockResolvedValue({
      data: { directory: readyDirectory({ status: 'failed' }), preview: [] },
    });

    const { result } = renderHook(() => useDirectoryUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.uploadedDirectory).toBeNull();
  });

  it('ignores a second upload while one is in flight', async () => {
    let release;
    vi.mocked(automationService.uploadDirectory).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ data: { directory: readyDirectory(), preview: PREVIEW } });
      })
    );

    const { result } = renderHook(() => useDirectoryUpload());

    act(() => result.current.selectFile(makeFile()));

    act(() => {
      result.current.upload();
    });

    await act(async () => {
      await result.current.upload();
    });

    expect(automationService.uploadDirectory).toHaveBeenCalledTimes(1);

    await act(async () => {
      release();
    });
  });

  it('clears a stale error when a new file is chosen', async () => {
    vi.mocked(automationService.uploadDirectory).mockRejectedValue(
      new ApiError('nope', 422, 'VALIDATION_ERROR')
    );

    const { result } = renderHook(() => useDirectoryUpload());

    act(() => result.current.selectFile(makeFile()));
    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).not.toBeNull();

    act(() => result.current.selectFile(makeFile('other.csv')));

    await waitFor(() => expect(result.current.error).toBeNull());
  });
});

describe('useEmployeeDirectories', () => {
  it('loads the ready directories from the backend', async () => {
    vi.mocked(automationService.listDirectories).mockResolvedValue([readyDirectory()]);

    const { result } = renderHook(() => useEmployeeDirectories());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.directories).toHaveLength(1);
    expect(result.current.failedDirectories).toEqual([]);
  });

  it('keeps a rejected directory out of the selectable list', async () => {
    vi.mocked(automationService.listDirectories).mockResolvedValue([
      readyDirectory(),
      readyDirectory({ directory_id: 'dir-002', status: 'failed' }),
    ]);

    const { result } = renderHook(() => useEmployeeDirectories());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.directories).toHaveLength(1);
    expect(result.current.failedDirectories).toHaveLength(1);
  });

  it('reports a listing failure without throwing', async () => {
    vi.mocked(automationService.listDirectories).mockRejectedValue(
      new ApiError('Could not reach the backend.', 0, 'NETWORK_ERROR')
    );

    const { result } = renderHook(() => useEmployeeDirectories());

    await waitFor(() => expect(result.current.error).not.toBeNull());

    expect(result.current.directories).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it('adds a newly uploaded directory without refetching', async () => {
    vi.mocked(automationService.listDirectories).mockResolvedValue([]);

    const { result } = renderHook(() => useEmployeeDirectories());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.addDirectory(readyDirectory()));

    expect(result.current.directories).toHaveLength(1);
    expect(automationService.listDirectories).toHaveBeenCalledTimes(1);
  });

  it('replaces rather than duplicates an existing entry', async () => {
    vi.mocked(automationService.listDirectories).mockResolvedValue([readyDirectory()]);

    const { result } = renderHook(() => useEmployeeDirectories());

    await waitFor(() => expect(result.current.directories).toHaveLength(1));

    act(() => result.current.addDirectory(readyDirectory({ employee_count: 9 })));

    expect(result.current.directories).toHaveLength(1);
    expect(result.current.directories[0].employee_count).toBe(9);
  });

  it('ignores an entry with no identifier', async () => {
    const { result } = renderHook(() => useEmployeeDirectories());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.addDirectory({ filename: 'broken.csv' }));

    expect(result.current.directories).toEqual([]);
  });
});