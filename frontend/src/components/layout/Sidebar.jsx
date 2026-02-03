/**
 * Sidebar with stats and document management
 */

import { StatsPanel } from '../stats/StatsPanel';
import { DocumentPanel } from '../documents/DocumentPanel';

export function Sidebar({ onClose }) {
  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header with close button (mobile) */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 lg:hidden">
        <h2 className="font-semibold text-gray-900">Panel</h2>
        <button
          onClick={onClose}
          className="p-2 rounded-lg hover:bg-gray-100"
          aria-label="Cerrar panel"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <StatsPanel />
        <DocumentPanel />
      </div>
    </div>
  );
}

export default Sidebar;
