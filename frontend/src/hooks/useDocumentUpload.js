import { useCallback, useState } from 'react';
import {
  hasSupportedExtension,
  knowledgeService,
  SUPPORTED_UPLOAD_LABEL,
} from '../services/knowledgeService';

/**
 * Upload one document to the Knowledge Agent and track the attempt.
 *
 * Three states are kept deliberately separate, because conflating them is how a
 * failed upload ends up looking successful:
 *   - `selectedFile`  what the user picked, not yet sent
 *   - `indexedDocument` set only after the backend confirms indexing
 *   - `error` set only after the request actually fails
 *
 * `upload` never fabricates a result. Success is whatever the backend reports,
 * and a 201 whose document is not `indexed` is treated as a failure rather than
 * optimistically shown as done.
 *
 * @returns {{
 *   selectedFile: File|null,
 *   selectFile: (file: File|null) => void,
 *   isUploading: boolean,
 *   isLoading: boolean,
 *   indexedDocument: object|null,
 *   error: Error|null,
 *   upload: (file?: File) => Promise<object|null>,
 *   reset: () => void,
 * }}
 */
export function useDocumentUpload() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [indexedDocument, setIndexedDocument] = useState(null);
  const [error, setError] = useState(null);

  /**
   * Record the chosen file, clearing any previous outcome.
   *
   * @param {File|null} file
   */
  const selectFile = useCallback((file) => {
    setSelectedFile(file || null);
    setError(null);
    setIndexedDocument(null);
  }, []);

  /**
   * Upload a file and index it.
   *
   * Refuses to start while another upload is in flight, which is what prevents
   * a double click from sending the same document twice.
   *
   * @param {File} [file] Defaults to the currently selected file.
   * @returns {Promise<object|null>} The indexed document, or null on failure.
   */
  const upload = useCallback(async (file) => {
    const target = file || selectedFile;

    if (!target || isUploading) return null;

    if (!hasSupportedExtension(target.name)) {
      setError(
        new Error(`Unsupported file type. Accepted formats: ${SUPPORTED_UPLOAD_LABEL}.`)
      );
      setIndexedDocument(null);
      return null;
    }

    setIsUploading(true);
    setError(null);
    setIndexedDocument(null);

    try {
      const response = await knowledgeService.uploadDocument(target);
      const document = response?.data?.document || null;

      // The backend answers 201 only after indexing. Guard anyway: a 201 with a
      // non-indexed document must not be rendered as a success.
      if (!document || document.status !== 'indexed') {
        setError(new Error('The document was received but was not indexed.'));
        return null;
      }

      setIndexedDocument(document);

      return document;
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
    setIndexedDocument(null);
    setError(null);
  }, []);

  return {
    selectedFile,
    selectFile,
    isUploading,
    isLoading: isUploading,
    indexedDocument,
    error,
    upload,
    reset,
  };
}