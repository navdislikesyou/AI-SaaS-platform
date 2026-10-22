/**
 * Upload one dataset for the Performance Analyzer and track the attempt.
 *
 * Three states are kept deliberately separate, because conflating them is how a
 * failed upload ends up looking successful:
 *   - `selectedFile`   what the user picked, not yet sent
 *   - `uploadedDataset` set only after the backend confirms it stored the file
 *   - `error`           set only after the request actually fails
 *
 * A dataset is only ever reported as uploaded when the backend says so. There is
 * no optimistic state here: the whole point of uploading is that the file now
 * exists where a background job can read it, and that cannot be assumed.
 */

import { useCallback, useState } from 'react';
import {
  hasSupportedDatasetExtension,
  performanceService,
  SUPPORTED_DATASET_LABEL,
} from '../services/performanceService';

/**
 * Render a byte count for display, e.g. "1.8 MB".
 *
 * @param {number} bytes
 * @returns {string}
 */
function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—';

  if (bytes < 1024) return `${bytes} B`;

  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Describe an upload failure in terms the user can act on.
 *
 * The backend sends a specific message for each rejection it anticipates, and
 * that message is more useful than anything generic. The status branches only
 * cover what the backend cannot describe, such as a network failure that never
 * reached it.
 *
 * @param {Error|null} error
 * @returns {string} An empty string when there is nothing to report.
 */
function describeDatasetError(error) {
  if (!error) return '';

  if (error.code === 'VALIDATION_ERROR' && error.message) return error.message;

  if (error.code === 'DATASET_NOT_FOUND' && error.message) return error.message;

  if (error.status === 0) {
    return 'Could not reach the backend. Check that the API is running and try again.';
  }

  if (error.status === 413) {
    return 'That file is too large to upload.';
  }

  return error.message || `Upload failed with status ${error.status}.`;
}

/**
 * Manage the dataset file picker and its upload.
 *
 * The extension and the size are checked before the request is made so a wrong
 * or oversized file fails instantly with a clear message. The backend
 * revalidates regardless, so this is a convenience and never the security
 * boundary.
 *
 * @param {{maxBytes?: number}} [options] The server-reported upload limit. A
 *   limit of zero means the limit is not known yet, and no size check is made.
 * @returns {{
 *   selectedFile: File|null,
 *   selectFile: (file: File|null) => void,
 *   isUploading: boolean,
 *   uploadedDataset: object|null,
 *   error: Error|null,
 *   errorMessage: string,
 *   upload: (file?: File) => Promise<object|null>,
 *   reset: () => void,
 * }}
 */
export function useDatasetUpload({ maxBytes = 0 } = {}) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedDataset, setUploadedDataset] = useState(null);
  const [error, setError] = useState(null);

  /**
   * Record the chosen file, clearing any previous outcome.
   *
   * @param {File|null} file
   */
  const selectFile = useCallback((file) => {
    setSelectedFile(file || null);
    setError(null);
    setUploadedDataset(null);
  }, []);

  /**
   * Upload a file so a background job can read it.
   *
   * Refuses to start while another upload is in flight, which is what prevents a
   * double click from sending the same dataset twice.
   *
   * @param {File} [file] Defaults to the currently selected file.
   * @returns {Promise<object|null>} The stored dataset, or null on failure.
   */
  const upload = useCallback(
    async (file) => {
      const target = file || selectedFile;

      if (!target || isUploading) return null;

      if (!hasSupportedDatasetExtension(target.name)) {
        setError(
          new Error(
            `Unsupported file type. Accepted formats: ${SUPPORTED_DATASET_LABEL}.`
          )
        );
        setUploadedDataset(null);
        return null;
      }

      // The limit comes from the server, so the browser never states a number
      // that could drift from configuration. The server enforces it too; this
      // only saves the user from uploading a file that would be refused.
      if (maxBytes > 0 && target.size > maxBytes) {
        setError(
          new Error(
            `That file is too large to upload. The maximum size is ${formatBytes(
              maxBytes
            )}.`
          )
        );
        setUploadedDataset(null);
        return null;
      }

      setIsUploading(true);
      setError(null);
      setUploadedDataset(null);

      try {
        const response = await performanceService.uploadDataset(target);
        const dataset = response?.data?.dataset || null;

        // A 201 whose dataset is absent or unusable must not be rendered as a
        // success, or the selector would offer something a job cannot read.
        if (!dataset?.dataset_id || dataset.status !== 'ready') {
          setError(new Error('The dataset was received but was not stored as usable.'));
          return null;
        }

        setUploadedDataset(dataset);

        return dataset;
      } catch (err) {
        setError(err);

        return null;
      } finally {
        setIsUploading(false);
      }
    },
    [isUploading, maxBytes, selectedFile]
  );

  /**
   * Clear the selected file and any previous outcome.
   */
  const reset = useCallback(() => {
    setSelectedFile(null);
    setUploadedDataset(null);
    setError(null);
  }, []);

  return {
    selectedFile,
    selectFile,
    isUploading,
    isLoading: isUploading,
    uploadedDataset,
    error,
    errorMessage: describeDatasetError(error),
    upload,
    reset,
  };
}