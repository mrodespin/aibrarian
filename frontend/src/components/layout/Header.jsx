/**
 * Application header with service status
 */

import { useApp } from '../../context/AppContext';
import { Badge } from '../common';

export function Header({ onMenuClick }) {
  const { health } = useApp();

  return (
    <header className="bg-bg-850/80 backdrop-blur-md border-b border-bg-700 px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {/* Mobile menu button */}
          <button
            onClick={onMenuClick}
            className="lg:hidden p-2 rounded-lg hover:bg-bg-800 text-text-100 transition-colors"
            aria-label="Toggle menu"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* Logo and title */}
          <div className="flex items-center gap-2">
            <span className="text-2xl">📚</span>
            <h1 className="text-xl font-bold bg-gradient-to-r from-accent-400 to-violet-500 bg-clip-text text-transparent">
              Bibliotecario-IA
            </h1>
          </div>
        </div>

        {/* Service status badges */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${health.api ? 'bg-accent-500 animate-pulse shadow-lg shadow-accent-500/50' : 'bg-error-500'}`} />
            <span className="text-sm font-medium text-text-200">API</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${health.ollama ? 'bg-accent-500 animate-pulse shadow-lg shadow-accent-500/50' : 'bg-error-500'}`} />
            <span className="text-sm font-medium text-text-200">Ollama</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${health.chromadb ? 'bg-accent-500 animate-pulse shadow-lg shadow-accent-500/50' : 'bg-error-500'}`} />
            <span className="text-sm font-medium text-text-200">ChromaDB</span>
          </div>
        </div>
      </div>
    </header>
  );
}

export default Header;
