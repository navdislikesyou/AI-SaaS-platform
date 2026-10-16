/**
 * Tests for the Knowledge document upload hooks.
 *
 * `knowledgeService` is mocked, so no network request is made and no real
 * document is sent anywhere. These tests cover the states the page depends on:
 * selected file, in-flight upload, confirmed index, and a failure that must not
 * be presented as success.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../services/api';
import { knowledgeService } from '../services/knowledgeService';
import { useDocumentUpload } from './useDocumentUpload';
import { useKnowledgeDocuments } from './useKnowledgeDocuments';

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

function makeFile(name = 'handbook.pdf', type = 'application/pdf') {
  return new File(['%PDF-1.7 content'], name, { type });
}

const INDEXED_DOCUMENT = {
  document_id: 'abc123',
  filename: 'handbook.pdf',
  extension: '.pdf',
  size_bytes: 1024,
  status: 'indexed',
  chunk_count: 4,
  uploaded_at: '2026-10-13T14:22:01+00:00',
};

beforeEach(() => {
  vi.mocked(knowledgeService.uploadDocument).mockReset();
  vi.mocked(knowledgeService.listDocuments).mockReset();
});

describe('useDocumentUpload', () => {
  it('starts with no file, no upload in flight, and no document', () => {
    const { result } = renderHook(() => useDocumentUpload());

    expect(result.current.selectedFile).toBeNull();
    expect(result.current.isUploading).toBe(false);
    expect(result.current.indexedDocument).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('holds the selected file before anything is sent', () => {
    const { result } = renderHook(() => useDocumentUpload());
    const file = makeFile();

    act(() => result.current.selectFile(file));

    expect(result.current.selectedFile).toBe(file);
    expect(knowledgeService.uploadDocument).not.toHaveBeenCalled();
  });

  it('reports the indexed document only after the backend confirms it', async () => {
    vi.mocked(knowledgeService.uploadDocument).mockResolvedValue({
      success: true,
      data: { document: INDEXED_DOCUMENT },
    });

    const { result } = renderHook(() => useDocumentUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(knowledgeService.uploadDocument).toHaveBeenCalledTimes(1);
    expect(result.current.indexedDocument).toEqual(INDEXED_DOCUMENT);
    expect(result.current.isUploading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('marks the upload in flight and clears it afterwards', async () => {
    let release;
    vi.mocked(knowledgeService.uploadDocument).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ success: true, data: { document: INDEXED_DOCUMENT } });
      })
    );

    const { result } = renderHook(() => useDocumentUpload());

    act(() => result.current.selectFile(makeFile()));

    let uploadPromise;
    act(() => {
      uploadPromise = result.current.upload();
    });

    await waitFor(() => expect(result.current.isUploading).toBe(true));
    expect(result.current.indexedDocument).toBeNull();

    await act(async () => {
      release();
      await uploadPromise;
    });

    expect(result.current.isUploading).toBe(false);
  });

  it('ignores a second upload while one is in flight', async () => {
    let release;
    vi.mocked(knowledgeService.uploadDocument).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve({ success: true, data: { document: INDEXED_DOCUMENT } });
      })
    );

    const { result } = renderHook(() => useDocumentUpload());

    act(() => result.current.selectFile(makeFile()));

    let firstUpload;
    act(() => {
      firstUpload = result.current.upload();
    });

    await waitFor(() => expect(result.current.isUploading).toBe(true));

    await act(async () => {
      // A double click, or an impatient second attempt.
      await result.current.upload();
    });

    expect(knowledgeService.uploadDocument).toHaveBeenCalledTimes(1);

    await act(async () => {
      release();
      await firstUpload;
    });
  });

  it('surfaces a backend rejection and does not claim a document was indexed', async () => {
    // A .pdf name passes the client-side extension filter, so this exercises
    // the backend's own rejection, which is what the user ultimately sees.
    vi.mocked(knowledgeService.uploadDocument).mockRejectedValue(
      new ApiError("'handbook.pdf' is not a readable PDF.", 422, 'VALIDATION_ERROR')
    );

    const { result } = renderHook(() => useDocumentUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error.message).toContain('not a readable PDF');
    expect(result.current.indexedDocument).toBeNull();
    expect(result.current.isUploading).toBe(false);
  });

  it('rejects an unsupported extension without calling the backend', async () => {
    const { result } = renderHook(() => useDocumentUpload());

    act(() => result.current.selectFile(makeFile('payload.exe', 'application/octet-stream')));

    await act(async () => {
      await result.current.upload();
    });

    expect(knowledgeService.uploadDocument).not.toHaveBeenCalled();
    expect(result.current.error.message).toContain('Unsupported file type');
    expect(result.current.indexedDocument).toBeNull();
  });

  it('treats a 201 without an indexed document as a failure', async () => {
    vi.mocked(knowledgeService.uploadDocument).mockResolvedValue({
      success: true,
      data: { document: { ...INDEXED_DOCUMENT, status: 'failed' } },
    });

    const { result } = renderHook(() => useDocumentUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.indexedDocument).toBeNull();
    expect(result.current.error).toBeTruthy();
  });

  it('clears a previous outcome when a new file is chosen', async () => {
    vi.mocked(knowledgeService.uploadDocument).mockResolvedValue({
      success: true,
      data: { document: INDEXED_DOCUMENT },
    });

    const { result } = renderHook(() => useDocumentUpload());

    act(() => result.current.selectFile(makeFile()));

    await act(async () => {
      await result.current.upload();
    });

    expect(result.current.indexedDocument).toBeTruthy();

    act(() => result.current.selectFile(makeFile('second.pdf')));

    expect(result.current.indexedDocument).toBeNull();
    expect(result.current.error).toBeNull();
  });
});

describe('useKnowledgeDocuments', () => {
  it('loads indexed documents on mount', async () => {
    vi.mocked(knowledgeService.listDocuments).mockResolvedValue([INDEXED_DOCUMENT]);

    const { result } = renderHook(() => useKnowledgeDocuments());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.documents).toEqual([INDEXED_DOCUMENT]);
    expect(result.current.error).toBeNull();
  });

  it('keeps failed documents out of the selectable list', async () => {
    vi.mocked(knowledgeService.listDocuments).mockResolvedValue([
      INDEXED_DOCUMENT,
      { ...INDEXED_DOCUMENT, document_id: 'failed1', status: 'failed' },
    ]);

    const { result } = renderHook(() => useKnowledgeDocuments());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.documents).toHaveLength(1);
    expect(result.current.failedDocuments).toHaveLength(1);
    expect(result.current.failedDocuments[0].document_id).toBe('failed1');
  });

  it('reports a listing failure without throwing', async () => {
    vi.mocked(knowledgeService.listDocuments).mockRejectedValue(
      new ApiError('backend is down', 500)
    );

    const { result } = renderHook(() => useKnowledgeDocuments());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.error).toBeTruthy();
    expect(result.current.documents).toEqual([]);
  });

  it('treats an empty backend listing as no documents', async () => {
    vi.mocked(knowledgeService.listDocuments).mockResolvedValue([]);

    const { result } = renderHook(() => useKnowledgeDocuments());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.documents).toEqual([]);
    expect(result.current.failedDocuments).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('puts a newly indexed document at the head without a refetch', async () => {
    vi.mocked(knowledgeService.listDocuments).mockResolvedValue([]);

    const { result } = renderHook(() => useKnowledgeDocuments());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.addDocument(INDEXED_DOCUMENT));

    expect(result.current.documents).toEqual([INDEXED_DOCUMENT]);
    expect(knowledgeService.listDocuments).toHaveBeenCalledTimes(1);
  });

  it('ignores a document with no identifier', async () => {
    vi.mocked(knowledgeService.listDocuments).mockResolvedValue([]);

    const { result } = renderHook(() => useKnowledgeDocuments());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.addDocument({ filename: 'nameless.pdf' }));

    expect(result.current.documents).toEqual([]);
  });
});