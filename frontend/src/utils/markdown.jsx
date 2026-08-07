/**
 * Component that renders simple markdown as HTML.
 * The conversion logic lives in utils/renderMarkdown.js.
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
