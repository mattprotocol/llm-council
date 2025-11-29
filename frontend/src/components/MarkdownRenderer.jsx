import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useState, useEffect, useRef } from 'react';
import './MarkdownRenderer.css';

// Mermaid diagram component with lazy loading
function MermaidDiagram({ code }) {
  const containerRef = useRef(null);
  const [svg, setSvg] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    
    const renderMermaid = async () => {
      try {
        // Dynamically import mermaid only when needed
        const mermaid = (await import('mermaid')).default;
        
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'loose',
          fontFamily: 'inherit',
        });
        
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, code);
        
        if (isMounted) {
          setSvg(svg);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message);
          setLoading(false);
        }
      }
    };
    
    renderMermaid();
    
    return () => {
      isMounted = false;
    };
  }, [code]);

  if (loading) {
    return <div className="mermaid-loading">Loading diagram...</div>;
  }

  if (error) {
    return (
      <div className="mermaid-error">
        <span>⚠️ Diagram error: {error}</span>
        <pre>{code}</pre>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef}
      className="mermaid-container"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

// Custom code block component with syntax highlighting and mermaid support
function CodeBlock({ node, inline, className, children, ...props }) {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  const code = String(children).replace(/\n$/, '');

  // Handle mermaid diagrams
  if (language === 'mermaid') {
    return <MermaidDiagram code={code} />;
  }

  // Inline code
  if (inline) {
    return (
      <code className="inline-code" {...props}>
        {children}
      </code>
    );
  }

  // Code block with syntax highlighting
  return (
    <div className="code-block-wrapper">
      {language && <span className="code-language">{language}</span>}
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={language || 'text'}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: '0 0 6px 6px',
          fontSize: '13px',
        }}
        {...props}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

/**
 * Enhanced markdown renderer with support for:
 * - GitHub Flavored Markdown (tables, strikethrough, task lists, etc.)
 * - Syntax highlighted code blocks
 * - Mermaid diagrams
 * - Raw HTML (for advanced formatting)
 */
export default function MarkdownRenderer({ children, className = '' }) {
  return (
    <div className={`markdown-renderer ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          code: CodeBlock,
          // Enhance table styling
          table: ({ node, ...props }) => (
            <div className="table-wrapper">
              <table {...props} />
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
