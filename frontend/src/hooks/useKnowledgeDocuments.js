import { useCallback, useEffect, useState } from 'react';
import { knowledgeService } from '../services/knowledgeService';

/**
 * Load the documents the backend has indexed.
 *
 * The backend manifest is the source of truth for the document selector.
 * Documents that failed to index come back with `status: 'failed'` and are kept
 * out of `documents`, so an unqueryable document is never offered as a choice.
 *
 * @returns {{
 *   documents: Array<object>,
 *   failedDocuments: Array<object>,
 *   isLoading: boolean,
 *   error: Error|null,
 *   refresh: () => Promise<void>,
 *   addDocument: (document: object) => void,
 * }}
 */
export function useKnowledgeDocuments() {
  const [documents, setDocuments] = useState([]);
  const [failedDocuments, setFailedDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  /**
   * Split a backend listing into indexed and failed documents.
   *
   * @param {Array<object>} all
   */
  const applyListing = useCallback((all) => {
    const rows = Array.isArray(all) ? all : [];

    setDocuments(rows.filter((row) => row?.status === 'indexed'));
    setFailedDocuments(rows.filter((row) => row?.status !== 'indexed'));
  }, []);

  /**
   * Reload the document list from the backend.
   */
  const refresh = useCallback(async () => {
    setIsLoading(true);

    try {
      applyListing(await knowledgeService.listDocuments());
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setIsLoading(false);
    }
  }, [applyListing]);

  useEffect(() => {
    let mounted = true;

    knowledgeService
      .listDocuments()
      .then((all) => {
        if (mounted) applyListing(all);
      })
      .catch((err) => {
        if (mounted) setError(err);
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [applyListing]);

  /**
   * Insert a newly indexed document at the head of the list.
   *
   * Used after an upload so the selector updates without a second round trip.
   * The backend remains authoritative; this only avoids a redundant refetch.
   *
   * @param {object} document
   */
  const addDocument = useCallback((document) => {
    if (!document?.document_id) return;

    setDocuments((current) => [
      document,
      ...current.filter((row) => row.document_id !== document.document_id),
    ]);
  }, []);

  return {
    documents,
    failedDocuments,
    isLoading,
    error,
    refresh,
    addDocument,
  };
}