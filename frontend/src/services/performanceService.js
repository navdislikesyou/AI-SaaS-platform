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

export const PERFORMANCE_OPERATIONS = [
  'load_dataset',
  'compute_kpis',
  'compare_periods',
  'analyze',
  'visualize',
];

// Lifecycle states the backend reports. Terminal states stop polling.
export const TERMINAL_JOB_STATUSES = ['completed', 'failed'];

// Reserved identifier for the dataset that ships inside the agent package. The
// backend resolves this to a configured server-side path, which is what lets a
// browser select a dataset without ever naming a file.
export const SAMPLE_DATASET_ID = 'sample';

/**
 * Extensions the backend accepts for an uploaded dataset.
 *
 * This mirrors `SUPPORTED_EXTENSIONS` in
 * `backend/app/services/dataset_upload.py`. It is deliberately narrower than
 * what the agent's loader will attempt: the loader also lists `.xls`, but that
 * needs the xlrd engine, which is not a dependency, so it is refused at upload
 * instead of failing later inside a job. This list only filters the file picker;
 * the backend revalidates everything.
 */
export const SUPPORTED_DATASET_EXTENSIONS = ['.csv', '.xlsx'];

/** `accept` attribute value for the dataset file input. */
export const DATASET_UPLOAD_ACCEPT = SUPPORTED_DATASET_EXTENSIONS.join(',');

/** Human-readable format list, for UI copy. */
export const SUPPORTED_DATASET_LABEL = SUPPORTED_DATASET_EXTENSIONS.join(', ');

/** Field name the backend expects for the uploaded file. */
export const DATASET_UPLOAD_FIELD = 'file';

/**
 * Report whether a filename has an extension the backend accepts.
 *
 * @param {string} filename
 * @returns {boolean}
 */
export function hasSupportedDatasetExtension(filename) {
  if (typeof filename !== 'string') return false;

  const lower = filename.toLowerCase();

  return SUPPORTED_DATASET_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

export const performanceService = {
  /**
   * Fetch one generated chart.
   *
   * The chart is fetched through the shared API client rather than pointed at
   * with an `<img src>`, because the artifact endpoint is scoped to the
   * organization that owns the job and expects a bearer token. An image element
   * cannot send an Authorization header, so a direct request is refused with a
   * 404 and the preview would never render.
   *
   * The response comes back as a Blob so the caller can show it from an object
   * URL. Nothing here builds a filesystem path: the backend scopes the
   * artifact to the job that generated it.
   *
   * @param {string} jobId Identifier of the job that generated the chart.
   * @param {string} filename Bare filename from the job's artifacts.
   * @returns {Promise<Blob>} The chart image.
   */
  async fetchArtifact(jobId, filename) {
    const endpoint = `/performance/jobs/${encodeURIComponent(
      jobId,
    )}/artifacts/${encodeURIComponent(filename)}`;

    return apiClient.getBlob(endpoint);
  },

  /**
   * Submit a job for background execution.
   *
   * Pass `datasetId` for anything a browser selected: the server resolves it to
   * a file it controls, so no client-side path is involved. `filePath` remains
   * available for the server-side workflow that predates uploads, but the two
   * are mutually exclusive and sending both is rejected.
   *
   * @param {string} operation One of PERFORMANCE_OPERATIONS.
   * @param {string} [filePath] Server-side path. Omitted when datasetId is set.
   * @param {string} [datasetId] Uploaded dataset id, or SAMPLE_DATASET_ID.
   * @returns {Promise<{job_id: string, status: string, operation: string, created_at: string}>}
   */
  async createJob(operation, filePath, datasetId) {
    const payload = { operation };

    if (datasetId) {
      payload.dataset_id = datasetId;
    } else if (filePath) {
      payload.file_path = filePath;
    }

    const response = await apiClient.post('/performance/jobs', payload);

    return response?.data;
  },

  /**
   * Upload a dataset the browser selected.
   *
   * The request blocks until the server has validated and stored the file, which
   * is what lets the UI claim success honestly: a 201 means the dataset really
   * is on the server and really can be read.
   *
   * @param {File} file
   * @returns {Promise<object>} The standard envelope from the backend.
   */
  async uploadDataset(file) {
    const formData = new FormData();
    formData.append(DATASET_UPLOAD_FIELD, file);

    return apiClient.postForm('/performance/datasets', formData);
  },

  /**
   * List the datasets this backend instance can analyse.
   *
   * The response carries the packaged sample plus this instance's uploads, and
   * the server's own size limit, so the UI can state the real limit instead of
   * hardcoding a number that could drift from configuration.
   *
   * @returns {Promise<{datasets: Array<object>, max_upload_bytes: number, supported_extensions: string[]}>}
   */
  async listDatasets() {
    const response = await apiClient.get('/performance/datasets');

    return response?.data || { datasets: [], max_upload_bytes: 0, supported_extensions: [] };
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
