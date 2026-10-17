import { useCallback, useState } from 'react';
import {
  automationService,
  hasSupportedExtension,
  SUPPORTED_UPLOAD_LABEL,
} from '../services/automationService';

/**
 * Upload one employee directory to the Automation API and track the attempt.
 *
 * Three states are kept deliberately separate, because conflating them is how a
 * failed upload ends up looking successful:
 *   - `selectedFile`      what the user picked, not yet sent
 *   - `uploadedDirectory` set only after the backend confirms the records
 *   - `error`             set only after the request actually fails
 *
 * `upload` never fabricates a result. Success is whatever the backend reports,
 * and a 201 whose directory is not `ready` is treated as a failure rather than
 * optimistically shown as done.
 *
 * @returns {{
 *   selectedFile: File|null,
 *   selectFile: (file: File|null) => void,
 *   isUploading: boolean,
 *   isLoading: boolean,
 *   uploadedDirectory: object|null,
 *   preview: Array<object>,
 *   error: Error|null,
 *   upload: (file?: File) => Promise<object|null>,
 *   reset: () => void,
 * }}
 */
export function useDirectoryUpload() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadedDirectory, setUploadedDirectory] = useState(null);
  const [preview, setPreview] = useState([]);
  const [error, setError] = useState(null);

  /**
   * Record the chosen file, clearing any previous outcome.
   *
   * @param {File|null} file
   */
  const selectFile = useCallback((file) => {
    setSelectedFile(file || null);
    setError(null);
    setUploadedDirectory(null);
    setPreview([]);
  }, []);

  /**
   * Upload an employee directory.
   *
   * Refuses to start while another upload is in flight, which is what prevents a
   * double click from sending the same file twice.
   *
   * @param {File} [file] Defaults to the currently selected file.
   * @returns {Promise<object|null>} The stored directory, or null on failure.
   */
  const upload = useCallback(async (file) => {
    const target = file || selectedFile;

    if (!target || isUploading) return null;

    if (!hasSupportedExtension(target.name)) {
      setError(
        new Error(`Unsupported file type. Accepted formats: ${SUPPORTED_UPLOAD_LABEL}.`)
      );
      setUploadedDirectory(null);
      setPreview([]);
      return null;
    }

    setIsUploading(true);
    setError(null);
    setUploadedDirectory(null);
    setPreview([]);

    try {
      const response = await automationService.uploadDirectory(target);
      const directory = response?.data?.directory || null;

      // The backend answers 201 only once every record validated. Guard anyway:
      // a 201 with an unready directory must not be rendered as a success.
      if (!directory || directory.status !== 'ready') {
        setError(new Error('The file was received but its records were not accepted.'));
        return null;
      }

      setUploadedDirectory(directory);
      setPreview(Array.isArray(response?.data?.preview) ? response.data.preview : []);

      return directory;
    } catch (err) {
      setError(err);

      return null;
    } finally {
      setIsUploading(false);
    }
  }, [isUploading, selectedFile]);

  /**
   * Clear the selected file and any previous outcome.
   */
  const reset = useCallback(() => {
    setSelectedFile(null);
    setUploadedDirectory(null);
    setPreview([]);
    setError(null);
  }, []);

  return {
    selectedFile,
    selectFile,
    isUploading,
    isLoading: isUploading,
    uploadedDirectory,
    preview,
    error,
    upload,
    reset,
  };
}