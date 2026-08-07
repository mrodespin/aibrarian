/**
 * Application header with service status
 */

import { useApp } from '../../hooks/useApp';
import { useAuth } from '../../hooks/useAuth';
import { Badge } from '../common';
import { llmProviderLabel, vectorDbProviderLabel } from '../../utils/providerLabels';

export function Header({ onMenuClick }) {
  const { health } = useApp();
  const { user, logout } = useAuth();

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

        <div className="flex items-center gap-3">
          {/* Service status badges — hidden below lg (the same breakpoint
              Layout.jsx uses for the fixed/off-canvas sidebar): on mobile
              and tablet this same info already lives in the side panel
              (StatsPanel, via the menu button), with more detail and
              without crowding the logo and "Log out" — showing it here
              too on narrow screens was just duplicated noise. On desktop
              the sidebar is fixed, so this serves as a quick glance
              without opening anything. */}
          <div className="hidden lg:flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${health.api ? 'bg-accent-500 animate-pulse shadow-lg shadow-accent-500/50' : 'bg-error-500'}`} />
              <span className="text-sm font-medium text-text-200">API</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${health.llm ? 'bg-accent-500 animate-pulse shadow-lg shadow-accent-500/50' : 'bg-error-500'}`} />
              <span className="text-sm font-medium text-text-200">{llmProviderLabel(health.llmProvider)}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${health.vectorDb ? 'bg-accent-500 animate-pulse shadow-lg shadow-accent-500/50' : 'bg-error-500'}`} />
              <span className="text-sm font-medium text-text-200">{vectorDbProviderLabel(health.vectorDbProvider)}</span>
            </div>
          </div>

          {/* Session */}
          <span className="text-sm text-text-300 hidden sm:inline">{user?.email}</span>
          <button
            onClick={logout}
            className="text-sm font-medium text-text-200 hover:text-text-50 transition-colors px-2 py-1 rounded-lg hover:bg-bg-800 whitespace-nowrap"
            aria-label="Log out"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}

export default Header;
