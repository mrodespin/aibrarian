/**
 * Document sync form with tabs for different sources
 */

import { useState } from 'react';
import { syncApi } from '../../api';
import { useApp } from '../../context/AppContext';
import { Card, Button, Input, Alert, Spinner } from '../common';

const TABS = [
  { id: 'pdf', label: 'PDF' },
  { id: 'notion', label: 'Notion' },
];

export function SyncForm() {
  const { refreshStats } = useApp();
  const [activeTab, setActiveTab] = useState('pdf');
  const [selectedFile, setSelectedFile] = useState(null);
  const [notionId, setNotionId] = useState('');
  const [notionType, setNotionType] = useState('page'); // 'page' or 'database'
  const [isSyncing, setIsSyncing] = useState(false);
  const [result, setResult] = useState(null);

  const handleSync = async () => {
    setIsSyncing(true);
    setResult(null);

    try {
      let response;

      switch (activeTab) {
        case 'pdf':
          if (!selectedFile) {
            throw new Error('Selecciona un archivo PDF');
          }
          response = await syncApi.uploadFile(selectedFile);
          break;

        case 'notion':
          if (notionType === 'page') {
            if (!notionId.trim()) {
              throw new Error('Ingresa el ID de la página de Notion');
            }
            response = await syncApi.syncNotionPage(notionId.trim());
          } else {
            // Database: ID opcional, usa el del .env si está vacío
            response = await syncApi.syncNotionDatabase(notionId.trim() || null);
          }
          break;

        default:
          throw new Error('Tipo de sincronización no válido');
      }

      // Format success message based on response type
      let successMessage;
      if (response.chunks_created !== undefined) {
        // Single document sync (PDF or Notion page)
        successMessage = `Sincronizado: ${response.chunks_created} chunks creados`;
        if (response.message) {
          successMessage += ` - ${response.message}`;
        }
      } else if (response.total !== undefined) {
        // Batch sync (Notion database)
        const successful = response.successful ?? 0;
        const total = response.total ?? 0;
        successMessage = `Sincronizado: ${successful}/${total} documentos`;
        if (response.failed > 0) {
          successMessage += ` (${response.failed} fallidos)`;
        }
        // Add details if available
        if (response.results && response.results.length > 0) {
          const totalChunks = response.results.reduce(
            (sum, r) => sum + (r.chunks_created || 0), 0
          );
          successMessage += ` - ${totalChunks} chunks totales`;
        }
      } else {
        successMessage = response.message || 'Sincronización completada';
      }

      setResult({ success: true, message: successMessage });
      refreshStats();

      // Clear inputs on success
      setSelectedFile(null);
      setNotionId('');
      // Reset file input
      const fileInput = document.getElementById('pdf-file-input');
      if (fileInput) fileInput.value = '';

    } catch (err) {
      setResult({
        success: false,
        message: err.message || 'Error en la sincronización',
      });
    } finally {
      setIsSyncing(false);
    }
  };

  const canSync = () => {
    switch (activeTab) {
      case 'pdf':
        return selectedFile !== null;
      case 'notion':
        // Page requires ID, database can use .env default
        if (notionType === 'page') {
          return notionId.trim().length > 0;
        }
        return true; // Database can be empty (uses .env default)
      default:
        return false;
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setResult({ success: false, message: 'Solo se permiten archivos PDF' });
        e.target.value = '';
        return;
      }
      setSelectedFile(file);
      setResult(null);
    }
  };

  return (
    <Card title="Sincronizar Documentos">
      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-4 -mx-4 px-4">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id);
              setResult(null);
            }}
            className={`
              px-4 py-2 text-sm font-medium border-b-2 transition-colors
              ${activeTab === tab.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="space-y-4">
        {activeTab === 'pdf' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Seleccionar PDF
            </label>
            <input
              id="pdf-file-input"
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              disabled={isSyncing}
              className="block w-full text-sm text-gray-500
                file:mr-4 file:py-2 file:px-4
                file:rounded file:border-0
                file:text-sm file:font-medium
                file:bg-blue-50 file:text-blue-700
                hover:file:bg-blue-100
                disabled:opacity-50"
            />
            {selectedFile && (
              <p className="text-sm text-green-600 mt-1">
                Seleccionado: {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
              </p>
            )}
          </div>
        )}

        {activeTab === 'notion' && (
          <>
            <div className="flex gap-2 mb-2">
              <button
                onClick={() => setNotionType('page')}
                className={`px-3 py-1 text-sm rounded ${
                  notionType === 'page'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-gray-100 text-gray-600'
                }`}
              >
                Página
              </button>
              <button
                onClick={() => setNotionType('database')}
                className={`px-3 py-1 text-sm rounded ${
                  notionType === 'database'
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-gray-100 text-gray-600'
                }`}
              >
                Base de datos
              </button>
            </div>
            <div>
              <Input
                label={notionType === 'page' ? 'ID de página' : 'ID de base de datos (opcional)'}
                placeholder={notionType === 'page' ? 'abc123... (requerido)' : 'Vacío = usar configuración .env'}
                value={notionId}
                onChange={(e) => setNotionId(e.target.value)}
                disabled={isSyncing}
              />
              {notionType === 'database' && (
                <p className="text-xs text-gray-500 mt-1">
                  Deja vacío para usar la base de datos configurada en el servidor
                </p>
              )}
            </div>
          </>
        )}

        {/* Sync button */}
        <Button
          onClick={handleSync}
          disabled={isSyncing || !canSync()}
          className="w-full"
        >
          {isSyncing ? (
            <>
              <Spinner size="sm" className="mr-2" />
              Sincronizando...
            </>
          ) : (
            'Sincronizar'
          )}
        </Button>

        {/* Result message */}
        {result && (
          <Alert type={result.success ? 'success' : 'error'}>
            {result.message}
          </Alert>
        )}

        {/* Admin tip */}
        <p className="text-xs text-gray-400 mt-4 pt-3 border-t border-gray-100">
          💡 Para sincronización masiva, usa <code className="bg-gray-100 px-1 rounded">python scripts/sync_documents.py</code>
        </p>
      </div>
    </Card>
  );
}

export default SyncForm;
