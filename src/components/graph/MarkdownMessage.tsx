import ReactMarkdown, { Components } from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from '@/lib/utils';

interface MarkdownMessageProps {
  content: string;
  className?: string;
  onNodeClick?: (nodeId: string) => void;
}

export function MarkdownMessage({ content, className, onNodeClick }: MarkdownMessageProps) {
  const components: Components = {
    // Code blocks with syntax highlighting
    code(props) {
      const { children, className: codeClassName, ...rest } = props;
      const match = /language-(\w+)/.exec(codeClassName || '');
      const isInline = !match && !String(children).includes('\n');

      if (!isInline && match) {
        return (
          <SyntaxHighlighter
            style={oneDark}
            language={match[1]}
            PreTag="div"
            customStyle={{
              fontSize: '0.8rem',
              padding: '0.75rem',
              borderRadius: '0.375rem',
              marginTop: '0.5rem',
              marginBottom: '0.5rem',
            }}
          >
            {String(children).replace(/\n$/, '')}
          </SyntaxHighlighter>
        );
      }

      return (
        <code
          className={cn('bg-muted px-1.5 py-0.5 rounded text-sm font-mono')}
          {...rest}
        >
          {children}
        </code>
      );
    },
    // Custom paragraph styling
    p({ children }) {
      return <p className="mb-2 last:mb-0">{children}</p>;
    },
    // Custom list styling
    ul({ children }) {
      return <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>;
    },
    ol({ children }) {
      return <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>;
    },
    li({ children }) {
      return <li className="text-sm">{children}</li>;
    },
    // Custom heading styling
    h1({ children }) {
      return <h1 className="text-lg font-bold mb-2 mt-3 first:mt-0">{children}</h1>;
    },
    h2({ children }) {
      return <h2 className="text-base font-semibold mb-2 mt-3 first:mt-0">{children}</h2>;
    },
    h3({ children }) {
      return <h3 className="text-sm font-semibold mb-1 mt-2 first:mt-0">{children}</h3>;
    },
    // Strong/bold text
    strong({ children }) {
      return <strong className="font-semibold">{children}</strong>;
    },
    // Links - support node:// protocol for clickable navigation
    a({ href, children }) {
      // Check if this is a node link (node://node_id)
      if (href?.startsWith('node://')) {
        const nodeId = href.replace('node://', '');
        return (
          <button
            onClick={(e) => {
              e.preventDefault();
              onNodeClick?.(nodeId);
            }}
            className="text-primary hover:underline cursor-pointer font-medium"
          >
            {children}
          </button>
        );
      }

      // Regular external links
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          {children}
        </a>
      );
    },
    // Blockquotes
    blockquote({ children }) {
      return (
        <blockquote className="border-l-2 border-muted-foreground/30 pl-3 italic text-muted-foreground my-2">
          {children}
        </blockquote>
      );
    },
    // Horizontal rules
    hr() {
      return <hr className="border-border my-3" />;
    },
  };

  return (
    <div className={cn('prose prose-sm dark:prose-invert max-w-none', className)}>
      <ReactMarkdown components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
