/**
 * Tests for the Performance Analyzer client.
 *
 * The artifact fetch is the part that matters here. A generated chart lives
 * behind an endpoint that is scoped to the organization that owns the job, so
 * it has to be requested through the authenticated API client rather than
 * loaded as a plain image URL. These check the URL that is built and that the
 * request goes through that client, which is what carries the bearer token.
 */

import { describe, expect, it, vi } from 'vitest';

import { apiClient } from './api';
import { performanceService } from './performanceService';

describe('performanceService.fetchArtifact', () => {
  it('requests the artifact of the job that generated it', async () => {
    const blob = new Blob(['png-bytes'], { type: 'image/png' });
    const getBlob = vi.spyOn(apiClient, 'getBlob').mockResolvedValue(blob);

    const result = await performanceService.fetchArtifact(
      'job-1',
      'channel_profit.png'
    );

    expect(getBlob).toHaveBeenCalledTimes(1);
    expect(getBlob).toHaveBeenCalledWith(
      '/performance/jobs/job-1/artifacts/channel_profit.png'
    );
    expect(result).toBe(blob);
  });

  it('goes through the API client, which is what carries the bearer token', async () => {
    const getBlob = vi.spyOn(apiClient, 'getBlob').mockResolvedValue(new Blob(['png']));

    await performanceService.fetchArtifact('job-1', 'channel_profit.png');

    // The artifact must never be fetched as a bare URL from an image element:
    // that request carries no Authorization header and the server refuses it.
    expect(getBlob).toHaveBeenCalled();
  });

  it('encodes the filename so it cannot break out of the path', async () => {
    const getBlob = vi.spyOn(apiClient, 'getBlob').mockResolvedValue(new Blob(['png']));

    await performanceService.fetchArtifact('job-1', '../secret.png');

    expect(getBlob).toHaveBeenCalledWith(
      '/performance/jobs/job-1/artifacts/..%2Fsecret.png'
    );
  });

  it('propagates a failed artifact request to the caller', async () => {
    vi.spyOn(apiClient, 'getBlob').mockRejectedValue(new Error('not found'));

    await expect(
      performanceService.fetchArtifact('job-1', 'channel_profit.png')
    ).rejects.toThrow('not found');
  });
});
