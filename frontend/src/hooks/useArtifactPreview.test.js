/**
 * Tests for the chart preview hook.
 *
 * A generated chart is fetched through the authenticated API client and shown
 * from an object URL, because the artifact endpoint is scoped to the
 * organization that owns the job and an `<img src>` cannot carry a bearer
 * token. These check that the chart is fetched at all, that a failure becomes a
 * message rather than a broken image, and that the object URLs are released
 * instead of leaking.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../services/api';
import { performanceService } from '../services/performanceService';
import { useArtifactPreview } from './useArtifactPreview';

vi.mock('../services/performanceService', async (importOriginal) => {
  const actual = await importOriginal();

  return {
    ...actual,
    performanceService: {
      fetchArtifact: vi.fn(),
    },
  };
});

beforeEach(() => {
  vi.mocked(performanceService.fetchArtifact).mockReset();
});

describe('useArtifactPreview', () => {
  it('fetches the chart and exposes an object URL for it', async () => {
    vi.mocked(performanceService.fetchArtifact).mockResolvedValue(
      new Blob(['png-bytes'], { type: 'image/png' })
    );

    const { result } = renderHook(() => useArtifactPreview('job-1'));

    await act(async () => {
      await result.current.loadArtifact('channel_profit.png');
    });

    expect(performanceService.fetchArtifact).toHaveBeenCalledWith(
      'job-1',
      'channel_profit.png'
    );

    const url = result.current.artifactUrls['channel_profit.png'];

    expect(url).toBeTruthy();
    expect(url.startsWith('blob:')).toBe(true);
    expect(result.current.artifactErrors['channel_profit.png']).toBeUndefined();
  });

  it('reports a failed chart as a message rather than a broken image', async () => {
    vi.mocked(performanceService.fetchArtifact).mockRejectedValue(
      new ApiError("Artifact 'channel_profit.png' was not found.", 404, 'JOB_NOT_FOUND')
    );

    const { result } = renderHook(() => useArtifactPreview('job-1'));

    await act(async () => {
      await result.current.loadArtifact('channel_profit.png');
    });

    expect(result.current.artifactUrls['channel_profit.png']).toBeUndefined();
    expect(result.current.artifactErrors['channel_profit.png']).toMatch(
      /no longer available/i
    );
  });

  it('reports an expired session plainly', async () => {
    vi.mocked(performanceService.fetchArtifact).mockRejectedValue(
      new ApiError('Not authenticated.', 401, 'UNAUTHORIZED')
    );

    const { result } = renderHook(() => useArtifactPreview('job-1'));

    await act(async () => {
      await result.current.loadArtifact('channel_profit.png');
    });

    expect(result.current.artifactErrors['channel_profit.png']).toMatch(/session/i);
  });

  it('does not fetch anything without a job', async () => {
    const { result } = renderHook(() => useArtifactPreview(null));

    await act(async () => {
      await result.current.loadArtifact('channel_profit.png');
    });

    expect(performanceService.fetchArtifact).not.toHaveBeenCalled();
  });

  it('releases the previous object URL when a chart is loaded again', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL');

    vi.mocked(performanceService.fetchArtifact).mockResolvedValue(
      new Blob(['png-bytes'], { type: 'image/png' })
    );

    const { result } = renderHook(() => useArtifactPreview('job-1'));

    await act(async () => {
      await result.current.loadArtifact('channel_profit.png');
    });

    const first = result.current.artifactUrls['channel_profit.png'];

    await act(async () => {
      await result.current.loadArtifact('channel_profit.png');
    });

    expect(revoke).toHaveBeenCalledWith(first);
  });

  it('releases every object URL when the job changes', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL');

    vi.mocked(performanceService.fetchArtifact).mockResolvedValue(
      new Blob(['png-bytes'], { type: 'image/png' })
    );

    const { result, rerender } = renderHook(({ jobId }) => useArtifactPreview(jobId), {
      initialProps: { jobId: 'job-1' },
    });

    await act(async () => {
      await result.current.loadArtifact('channel_profit.png');
    });

    const url = result.current.artifactUrls['channel_profit.png'];

    rerender({ jobId: 'job-2' });

    await waitFor(() => expect(revoke).toHaveBeenCalledWith(url));

    // The chart of the previous job is not offered any more.
    expect(result.current.artifactUrls['channel_profit.png']).toBeUndefined();
  });
});
