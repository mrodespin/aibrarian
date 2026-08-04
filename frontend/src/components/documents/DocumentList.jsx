/**
 * Document list panel — explora la base de conocimiento sin pasar por el
 * chat (consume GET /documents, que a su vez no pasa por similarity
 * search, ver RAGService.list_known_documents en el backend).
 *
 * Por qué existe esto además del chat: preguntas agregadas tipo "¿cuántos
 * libros conoces?" no se pueden responder de forma fiable con RAG
 * semántico top-k (ver ADR / discusión de sync de Notion) — la forma
 * robusta de "explorar" el catálogo es un listado real, no una respuesta
 * generada. Inspirado en el glosario con buscador del Tutor Dev IA del
 * máster (misma idea: descubribilidad sin depender del LLM).
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { documentsApi } from '../../api';
import { useApp } from '../../context/AppContext';
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
      setError(err.message || 'No se pudo cargar la lista de documentos');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Carga inicial + recarga automática cada vez que cambia el nº de
  // documentos (SyncForm llama a refreshStats() al terminar un sync, así
  // que un sync nuevo se refleja aquí sin plumbing adicional)
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
      setError(err.message || 'No se pudo eliminar el documento');
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
    <Card title={`Documentos indexados (${documents.length})`}>
      <div className="space-y-3">
        <Input
          placeholder="Buscar documento..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          disabled={isLoading || documents.length === 0}
        />

        {error && <Alert type="error">{error}</Alert>}

        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-text-300">
            <Spinner size="md" className="mr-2" />
            Cargando documentos...
          </div>
        ) : documents.length === 0 ? (
          <p className="text-sm text-text-300 py-4 text-center">
            Todavía no hay documentos indexados.
          </p>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-text-300 py-4 text-center">
            Ningún documento coincide con "{search}".
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
                    aria-label={`Eliminar ${doc.title}`}
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
