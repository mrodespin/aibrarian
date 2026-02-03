/**
 * Main application layout
 * Responsive: sidebar collapses on mobile
 */

import { useState } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

export function Layout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="h-screen flex flex-col bg-bg-900">
      {/* Header */}
      <Header onMenuClick={() => setSidebarOpen(true)} />

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar - hidden on mobile, overlay on tablet, fixed on desktop */}
        <aside
          className={`
            fixed inset-y-0 left-0 z-40 w-80 bg-bg-850 border-r border-bg-700
            transform transition-transform duration-200 ease-in-out
            lg:relative lg:translate-x-0
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          `}
        >
          <Sidebar onClose={() => setSidebarOpen(false)} />
        </aside>

        {/* Overlay for mobile */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Main content */}
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}

export default Layout;
