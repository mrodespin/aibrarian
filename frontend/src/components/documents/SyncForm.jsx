/**
 * Document sync form with tabs for different sources
 */

import { useState } from 'react';
import { syncApi } from '../../api';
import { useApp } from '../../hooks/useApp';
import { Card, Button, Input, Alert, Spinner } from '../common';

const TABS = [
  {
    id: 'pdf',
    label: 'PDF',
    icon: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path d="M4 18h12V6h-4V2H4v16zm-2 1V0h10l4 4v16H2v-1z"/>
      </svg>
    )
  },
  {
    id: 'notion',
    label: 'Notion',
    icon: (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
        <path fillRule="evenodd" d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5z" clipRule="evenodd"/>
      </svg>
    )
  },
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
            throw new Error('Select a PDF file');
          }
          response = await syncApi.uploadFile(selectedFile);
          break;

        case 'notion':
          if (notionType === 'page') {
            if (!notionId.trim()) {
              throw new Error('Enter the Notion page ID');
            }
            response = await syncApi.syncNotionPage(notionId.trim());
          } else {
            // Database: ID is optional, uses the .env default if empty
            response = await syncApi.syncNotionDatabase(notionId.trim() || null);
          }
          break;

        default:
          throw new Error('Invalid sync type');
      }

      // Format success message based on response type
      let successMessage;
      if (response.chunks_created !== undefined) {
        // Single document sync (PDF or Notion page)
        successMessage = `Synced: ${response.chunks_created} chunks created`;
        if (response.message) {
          successMessage += ` - ${response.message}`;
        }
      } else if (response.total !== undefined) {
        // Batch sync (Notion database)
        const successful = response.successful ?? 0;
        const total = response.total ?? 0;
        successMessage = `Synced: ${successful}/${total} documents`;
        if (response.failed > 0) {
          successMessage += ` (${response.failed} failed)`;
        }
        // Add details if available
        if (response.results && response.results.length > 0) {
          const totalChunks = response.results.reduce(
            (sum, r) => sum + (r.chunks_created || 0), 0
          );
          successMessage += ` - ${totalChunks} chunks total`;
        }
      } else {
        successMessage = response.message || 'Sync completed';
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
        message: err.message || 'Sync failed',
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
        setResult({ success: false, message: 'Only PDF files are allowed' });
        e.target.value = '';
        return;
      }
      setSelectedFile(file);
      setResult(null);
    }
  };

  return (
    <Card title="Sync Documents">
      {/* Tabs */}
      <div className="flex border-b border-bg-700 mb-4 -mx-4 px-4">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id);
              setResult(null);
            }}
            className={`
              px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-2
              ${activeTab === tab.id
                ? 'border-accent-500 text-accent-400'
                : 'border-transparent text-text-300 hover:text-text-200'
              }
            `}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="space-y-4">
        {activeTab === 'pdf' && (
          <div>
            <label className="block text-sm font-medium text-text-100 mb-1">
              Select PDF
            </label>
            <input
              id="pdf-file-input"
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              disabled={isSyncing}
              className="block w-full text-sm text-text-200
                file:mr-4 file:py-2 file:px-4
                file:rounded-lg file:border file:border-bg-700
                file:text-sm file:font-medium
                file:bg-bg-800 file:text-text-100
                hover:file:bg-bg-700 hover:file:text-text-50
                file:transition-all file:cursor-pointer
                disabled:opacity-50"
            />
            {selectedFile && (
              <p className="text-sm text-success-400 mt-1">
                Selected: {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
              </p>
            )}
          </div>
        )}

        {activeTab === 'notion' && (
          <>
            <div className="flex gap-2 mb-2">
              <button
                onClick={() => setNotionType('page')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-all font-medium ${
                  notionType === 'page'
                    ? 'bg-accent-500/20 text-accent-400 border border-accent-500/50 shadow-sm shadow-accent-500/20'
                    : 'bg-bg-800 text-text-200 border border-bg-700 hover:bg-bg-700 hover:text-text-100'
                }`}
              >
                Page
              </button>
              <button
                onClick={() => setNotionType('database')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-all font-medium ${
                  notionType === 'database'
                    ? 'bg-accent-500/20 text-accent-400 border border-accent-500/50 shadow-sm shadow-accent-500/20'
                    : 'bg-bg-800 text-text-200 border border-bg-700 hover:bg-bg-700 hover:text-text-100'
                }`}
              >
                Database
              </button>
            </div>
            <div>
              <Input
                label={notionType === 'page' ? 'Page ID' : 'Database ID (optional)'}
                placeholder={notionType === 'page' ? 'abc123... (required)' : 'Empty = use .env config'}
                value={notionId}
                onChange={(e) => setNotionId(e.target.value)}
                disabled={isSyncing}
              />
              {notionType === 'database' && (
                <p className="text-xs text-text-300 mt-1">
                  Leave empty to use the database configured on the server
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
              Syncing...
            </>
          ) : (
            'Sync'
          )}
        </Button>

        {/* Result message */}
        {result && (
          <Alert type={result.success ? 'success' : 'error'}>
            {result.message}
          </Alert>
        )}

        {/* Admin tip */}
        <p className="text-xs text-text-300 mt-4 pt-3 border-t border-gray-100">
          💡 For bulk sync, use <code className="bg-bg-800 px-1 rounded">python scripts/sync_documents.py</code>
        </p>
      </div>
    </Card>
  );
}

export default SyncForm;
