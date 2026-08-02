/**
 * Simple markdown renderer
 * For full markdown support, consider adding react-markdown
 */

/**
 * Escapa entidades HTML para que el texto no pueda inyectar markup/scripts
 * cuando se inserta luego vía dangerouslySetInnerHTML.
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

export function MarkdownContent({ content, className = '' }) {
  return (
    <div
      className={`prose prose-sm max-w-none ${className}`}
      dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
    />
  );
}

export default MarkdownContent;
