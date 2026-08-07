/**
 * Componente que renderiza markdown simple como HTML.
 * La lógica de conversión vive en utils/renderMarkdown.js.
 */
import { renderMarkdown } from './renderMarkdown';

export function MarkdownContent({ content, className = '' }) {
  return (
    <div
      className={`prose prose-sm max-w-none ${className}`}
      dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
    />
  );
}

export default MarkdownContent;
