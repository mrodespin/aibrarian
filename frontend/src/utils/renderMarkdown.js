/**
 * Simple markdown renderer
 * For full markdown support, consider adding react-markdown
 *
 * Separated from markdown.jsx (which only exports the MarkdownContent
 * component) because react-refresh/only-export-components requires
 * that a file exporting a component not mix in exports of another kind
 * (here, a utility function) — otherwise Fast Refresh can't hot-reload
 * that file without losing React's state.
 */

/**
 * Escapes HTML entities so the text can't inject markup/scripts when
 * later inserted via dangerouslySetInnerHTML.
 */
function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function renderMarkdown(text) {
  if (!text) return '';

  return escapeHtml(text)
    // Code blocks (```...```)
    .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre class="bg-gray-800 text-gray-100 p-3 rounded-lg overflow-x-auto my-2 text-sm"><code>$2</code></pre>')
    // Inline code (`...`)
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-sm">$1</code>')
    // Bold (**...**)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    // Italic (*...*)
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // Headers (### ...)
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold mt-4 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold mt-4 mb-2">$1</h1>')
    // Lists (- ...)
    .replace(/^- (.+)$/gm, '<li class="ml-4">$1</li>')
    // Numbered lists (1. ...)
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    // Line breaks
    .replace(/\n/g, '<br />');
}

export default renderMarkdown;
