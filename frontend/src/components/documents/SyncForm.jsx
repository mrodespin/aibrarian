/**
 * Document sync form with tabs for different sources
 */

import { useState } from 'react';
import { syncApi } from '../../api';
import { useApp } from '../../context/AppContext';
import { Card, Button, Input, Alert, Spinner } from '../common';

const TABS = [
  { id: 'pdf', label: 'PDF' },
  { id: 'directory', label: 'Directorio' },
  { id: 'notion', label: 'Notion' },
];

export function SyncForm() {
  const { refreshStats } = useApp();
  const [activeTab, setActiveTab] = useState('pdf');
  const [filePath, setFilePath] = useState('');
  const [directoryPath, setDirectoryPath] = useState('');
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
          if (!filePath.trim()) {
            throw new Error('Ingresa la ruta del archivo PDF');
          }
          response = await syncApi.syncFile(filePath.trim());
          break;

        case 'directory':
          response = await syncApi.syncDirectory(directoryPath.trim() || null);
          break;

        case 'notion':
          if (!notionId.trim()) {
            throw new Error('Ingresa el ID de Notion');
          }
          if (notionType === 'page') {
            response = await syncApi.syncNotionPage(notionId.trim());
          } else {
            response = await syncApi.syncNotionDatabase(notionId.trim());
          }
          break;

        default:
          throw new Error('Tipo de sincronización no válido');
      }

      // Format success message
      let successMessage;
      if (response.chunks_created !== undefined) {
        successMessage = `Sincronizado: ${response.chunks_created} chunks creados`;
      } else if (response.total !== undefined) {
        successMessage = `Sincronizado: ${response.successful}/${response.total} documentos`;
      } else {
        successMessage = 'Sincronización completada';
      }

      setResult({ success: true, message: successMessage });
      refreshStats();

      // Clear inputs on success
      setFilePath('');
      setNotionId('');

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
        return filePath.trim().length > 0;
      case 'directory':
        return true; // Can sync with default directory
      case 'notion':
        return notionId.trim().length > 0;
      default:
        return false;
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
          <Input
            label="Ruta del archivo PDF"
            placeholder="/ruta/al/documento.pdf"
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
            disabled={isSyncing}
          />
        )}

        {activeTab === 'directory' && (
          <div>
            <Input
              label="Directorio (opcional)"
              placeholder="./data (por defecto)"
              value={directoryPath}
              onChange={(e) => setDirectoryPath(e.target.value)}
              disabled={isSyncing}
            />
            <p className="text-xs text-gray-500 mt-1">
              Deja vacío para usar el directorio por defecto (./data)
            </p>
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
            <Input
              label={notionType === 'page' ? 'ID de página' : 'ID de base de datos'}
              placeholder="abc123..."
              value={notionId}
              onChange={(e) => setNotionId(e.target.value)}
              disabled={isSyncing}
            />
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
      </div>
    </Card>
  );
}

export default SyncForm;
