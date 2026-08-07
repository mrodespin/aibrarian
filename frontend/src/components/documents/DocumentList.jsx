/**
 * Document list panel — browses the knowledge base without going
 * through the chat (consumes GET /documents, which in turn doesn't go
 * through similarity search, see RAGService.list_known_documents on
 * the backend).
 *
 * Why this exists in addition to the chat: aggregate questions like
 * "how many books do you know?" can't be answered reliably with
 * top-k semantic RAG (see the ADR / Notion sync discussion) — the
 * robust way to "browse" the catalog is a real listing, not a
 * generated answer. Same idea as any searchable glossary: discoverability
 * that doesn't depend on the LLM.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { documentsApi } from '../../api';
import { useApp } from '../../hooks/useApp';
import { Card, Badge, Button, Input, Alert, Spinner } from '../common';

const SOURCE_BADGE = {
  pdf: { label: 'PDF', variant: 'info' },
  notion: { label: 'Notion', variant: 'success' },
  unknown: { label: '?', variant: 'default' },
};

export function DocumentList() {
  const { stats, refreshStats } = useApp();
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [deletingId, setDeletingId] = useState(null);

  const fetchDocuments = useCallback(async () => {
    setError(null);
    try {
      const data = await documentsApi.list();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err.message || 'Could not load the document list');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load + automatic reload whenever the document count changes
  // (SyncForm calls refreshStats() when a sync finishes, so a new sync
  // shows up here with no extra plumbing needed)
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments, stats.documentCount]);

  const handleDelete = async (documentId) => {
    setDeletingId(documentId);
    try {
      await documentsApi.delete(documentId);
      setDocuments((prev) => prev.filter((d) => d.document_id !== documentId));
      refreshStats();
    } catch (err) {
      setError(err.message || 'Could not delete the document');
    } finally {
      setDeletingId(null);
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter((d) => d.title.toLowerCase().includes(q));
  }, [documents, search]);

  return (
    <Card title={`Indexed documents (${documents.length})`}>
      <div className="space-y-3">
        <Input
          placeholder="Search documents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          disabled={isLoading || documents.length === 0}
        />

        {error && <Alert type="error">{error}</Alert>}

        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-text-300">
            <Spinner size="md" className="mr-2" />
            Loading documents...
          </div>
        ) : documents.length === 0 ? (
          <p className="text-sm text-text-300 py-4 text-center">
            No documents indexed yet.
          </p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-text-300 py-4 text-center">
            No documents match "{search}".
          </p>
        ) : (
          <ul className="space-y-2 max-h-96 overflow-y-auto">
            {filtered.map((doc) => {
              const badge = SOURCE_BADGE[doc.source] || SOURCE_BADGE.unknown;
              return (
                <li
                  key={doc.document_id}
                  className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border border-bg-700 bg-bg-900"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-text-100 truncate">{doc.title}</p>
                    <p className="text-xs text-text-300">{doc.chunk_count} chunks</p>
                  </div>
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={deletingId === doc.document_id}
                    onClick={() => handleDelete(doc.document_id)}
                    aria-label={`Delete ${doc.title}`}
                  >
                    {deletingId === doc.document_id ? <Spinner size="sm" /> : '🗑️'}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
}

export default DocumentList;
