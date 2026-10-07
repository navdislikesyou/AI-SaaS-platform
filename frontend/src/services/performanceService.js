/**
 * Performance Analyzer job client.
 *
 * Performance is NOT reachable through POST /agents/execute. Its analysis is
 * CPU-bound and long running, so the backend serves it as a background job:
 * submit, receive 202 with a job id, then poll for the outcome.
 *
 * Job lifecycle: queued -> running -> completed | failed.
 *
 * Reuses the shared apiClient so base URL, X-Request-ID correlation, and
 * ApiError normalization stay in one place.
 */
import { apiClient } from './api';

const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export const PERFORMANCE_OPERATIONS = [
  'load_dataset',
  'compute_kpis',
  'compare_periods',
  'analyze',
  'visualize',
];

// Lifecycle states the backend reports. Terminal states stop polling.
export const TERMINAL_JOB_STATUSES = ['completed', 'failed'];

export const performanceService = {
  /**
   * URL for one generated chart.
   *
   * Returns a plain URL rather than fetching, so the browser loads the image
   * only when an <img> is actually mounted. Nothing here builds a filesystem
   * path: the backend scopes the artifact to the job that generated it.
   *
   * @param {string} jobId
   * @param {string} filename Bare filename from the job's artifacts.
   * @returns {string}
   */
  artifactUrl(jobId, filename) {
    return `${BASE_URL}/performance/jobs/${encodeURIComponent(
      jobId,
    )}/artifacts/${encodeURIComponent(filename)}`;
  },

  /**
   * Submit a job for background execution.
   *
   * @param {string} operation One of PERFORMANCE_OPERATIONS.
   * @param {string} filePath Server-side path to a .csv, .xlsx, or .xls file.
   * @returns {Promise<{job_id: string, status: string, operation: string, created_at: string}>}
   */
  async createJob(operation, filePath) {
    const response = await apiClient.post('/performance/jobs', {
      operation,
      file_path: filePath,
    });

    return response?.data;
  },

  /**
   * Fetch the current state of one job.
   *
   * @param {string} jobId Identifier returned by createJob.
   * @returns {Promise<object>} Full job status payload.
   */
  async getJob(jobId) {
    const response = await apiClient.get(`/performance/jobs/${jobId}`);

    return response?.data;
  },
};

export default performanceService;
