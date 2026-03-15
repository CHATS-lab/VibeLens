import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { Components } from "react-markdown";
import { CopyButton } from "./copy-button";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

function extractLanguage(className: string | undefined): string {
  if (!className) return "";
  const match = className.match(/language-(\w+)/);
  return match ? match[1] : "";
}

function MarkdownRendererInner({ content, className = "" }: MarkdownRendererProps) {
  const components: Components = {
    h1: ({ children }) => (
      <h1 className="text-lg font-semibold text-zinc-100 mt-4 mb-2">{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="text-base font-semibold text-zinc-100 mt-3 mb-1.5">{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="text-sm font-semibold text-zinc-100 mt-2.5 mb-1">{children}</h3>
    ),
    h4: ({ children }) => (
      <h4 className="text-sm font-medium text-zinc-200 mt-2 mb-1">{children}</h4>
    ),
    h5: ({ children }) => (
      <h5 className="text-xs font-medium text-zinc-200 mt-1.5 mb-0.5">{children}</h5>
    ),
    h6: ({ children }) => (
      <h6 className="text-xs font-medium text-zinc-300 mt-1.5 mb-0.5">{children}</h6>
    ),
    p: ({ children }) => (
      <p className="text-[13px] leading-relaxed text-zinc-200 my-1.5">{children}</p>
    ),
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
      >
        {children}
      </a>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-zinc-50">{children}</strong>
    ),
    em: ({ children }) => (
      <em className="italic text-zinc-300">{children}</em>
    ),
    code: ({ className: codeClassName, children }) => {
      const lang = extractLanguage(codeClassName);
      const hasHljsClass = codeClassName?.includes("hljs");
      const isBlock = lang || hasHljsClass;
      if (!isBlock) {
        return (
          <code className="px-1.5 py-0.5 rounded bg-zinc-800/80 text-cyan-300 text-[12px] font-mono">
            {children}
          </code>
        );
      }
      return (
        <code className={`${codeClassName || ""} text-[12px] font-mono`}>
          {children}
        </code>
      );
    },
    pre: ({ children }) => {
      const codeChild = children as React.ReactElement<{
        className?: string;
        children?: unknown;
      }>;
      const lang = extractLanguage(codeChild?.props?.className);
      const codeText = extractCodeText(codeChild);

      return (
        <div className="my-2 rounded-lg border border-zinc-700/60 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-800/80 border-b border-zinc-700/60">
            <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider">
              {lang || "code"}
            </span>
            <CopyButton text={codeText} />
          </div>
          <pre className="p-3 overflow-x-auto bg-zinc-900/60 text-[12px] leading-relaxed !m-0">
            {children}
          </pre>
        </div>
      );
    },
    ul: ({ children }) => (
      <ul className="list-disc list-outside pl-5 space-y-0.5 my-1.5 text-[13px] text-zinc-200">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="list-decimal list-outside pl-5 space-y-0.5 my-1.5 text-[13px] text-zinc-200">{children}</ol>
    ),
    li: ({ children }) => (
      <li className="leading-relaxed [&>p]:my-0 [&>p]:inline">{children}</li>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-l-2 border-zinc-600 pl-3 my-2 italic text-zinc-400">
        {children}
      </blockquote>
    ),
    table: ({ children }) => (
      <div className="my-2 overflow-x-auto rounded-lg border border-zinc-700/60">
        <table className="w-full text-[12px]">{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-zinc-900 text-zinc-300">{children}</thead>
    ),
    tr: ({ children }) => (
      <tr className="border-b border-zinc-700/40">{children}</tr>
    ),
    th: ({ children }) => (
      <th className="px-3 py-1.5 text-left font-medium text-zinc-300">{children}</th>
    ),
    td: ({ children }) => (
      <td className="px-3 py-1.5 text-zinc-400">{children}</td>
    ),
    hr: () => <hr className="border-zinc-700 my-3" />,
  };

  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function extractCodeText(codeChild: React.ReactElement<{ children?: unknown }> | null): string {
  if (!codeChild?.props?.children) return "";
  const raw = codeChild.props.children;
  if (typeof raw === "string") return raw.replace(/\n$/, "");
  if (Array.isArray(raw)) return (raw as unknown[]).map(String).join("").replace(/\n$/, "");
  return String(raw).replace(/\n$/, "");
}

export const MarkdownRenderer = memo(MarkdownRendererInner);
