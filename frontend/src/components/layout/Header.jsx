/**
 * Application header with service status
 */

import { useApp } from '../../context/AppContext';
import { Badge } from '../common';

export function Header({ onMenuClick }) {
  const { health } = useApp();

  return (
    <header className="bg-white border-b border-gray-200 px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {/* Mobile menu button */}
          <button
            onClick={onMenuClick}
            className="lg:hidden p-2 rounded-lg hover:bg-gray-100"
            aria-label="Toggle menu"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* Logo and title */}
          <div className="flex items-center gap-2">
            <span className="text-2xl">📚</span>
            <h1 className="text-xl font-bold text-gray-900">Bibliotecario-IA</h1>
          </div>
        </div>

        {/* Service status badges */}
        <div className="flex items-center gap-2">
          <Badge variant={health.ollama ? 'success' : 'error'}>
            Ollama {health.ollama ? 'ON' : 'OFF'}
          </Badge>
          <Badge variant={health.chromadb ? 'success' : 'error'}>
            ChromaDB {health.chromadb ? 'ON' : 'OFF'}
          </Badge>
        </div>
      </div>
    </header>
  );
}

export default Header;
