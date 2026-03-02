import { useState } from 'react';
import './ThinkBlockRenderer.css';

/**
 * Parses content containing <think>...</think> tags into segments.
 * Returns an array of { type: 'text' | 'think', content: string } objects.
 */
function parseThinkBlocks(text) {
  if (!text) return [{ type: 'text', content: '' }];

  const segments = [];
  const regex = /<think>([\s\S]*?)<\/think>/gi;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // Text before this think block
    if (match.index > lastIndex) {
      const before = text.slice(lastIndex, match.index).trim();
      if (before) segments.push({ type: 'text', content: before });
    }
    // The think block content
    segments.push({ type: 'think', content: match[1].trim() });
    lastIndex = match.index + match[0].length;
  }

  // Remaining text after last think block
  const remaining = text.slice(lastIndex).trim();
  if (remaining) segments.push({ type: 'text', content: remaining });

  // If no think blocks found, return original text
  if (segments.length === 0) {
    return [{ type: 'text', content: text }];
  }

  return segments;
}

/**
 * Renders content with collapsible <think> blocks.
 * Think blocks appear as collapsed "Reasoning" sections.
 * Regular content is passed through to the children render function.
 */
export default function ThinkBlockRenderer({ content, renderContent }) {
  const segments = parseThinkBlocks(content);
  const hasThinkBlocks = segments.some(s => s.type === 'think');

  if (!hasThinkBlocks) {
    return renderContent(content);
  }

  return (
    <div className="think-block-container">
      {segments.map((segment, index) =>
        segment.type === 'think' ? (
          <ThinkBlock key={index} content={segment.content} index={index} />
        ) : (
          <div key={index} className="think-block-text">
            {renderContent(segment.content)}
          </div>
        )
      )}
    </div>
  );
}

function ThinkBlock({ content, index }) {
  const [isOpen, setIsOpen] = useState(false);
  const lineCount = content.split('\n').length;

  return (
    <details
      className="think-block"
      open={isOpen}
      onToggle={(e) => setIsOpen(e.target.open)}
    >
      <summary className="think-block-summary">
        <span className="think-block-icon">
          {isOpen ? '\u25BE' : '\u25B8'}
        </span>
        <span className="think-block-label">Reasoning</span>
        <span className="think-block-lines">{lineCount} lines</span>
      </summary>
      <div className="think-block-content">
        {content}
      </div>
    </details>
  );
}

export { parseThinkBlocks };
