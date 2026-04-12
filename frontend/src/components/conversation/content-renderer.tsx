import { useState } from "react";
import type { ContentPart } from "../../types";
import { sanitizeText } from "../../utils";
import { MarkdownRenderer } from "../markdown-renderer";

interface ContentRendererProps {
  content: string | ContentPart[];
  className?: string;
}

export function ContentRenderer({ content, className }: ContentRendererProps) {
  if (typeof content === "string") {
    const cleaned = sanitizeText(content);
    if (!cleaned) return null;
    return <MarkdownRenderer content={cleaned} className={className} />;
  }

  if (!content.length) return null;

  return (
    <div className={className}>
      {content.map((part, i) => (
        <ContentPartView key={i} part={part} />
      ))}
    </div>
  );
}

function ContentPartView({ part }: { part: ContentPart }) {
  if (part.type === "text" && part.text) {
    const cleaned = sanitizeText(part.text);
    if (!cleaned) return null;
    return <MarkdownRenderer content={cleaned} />;
  }

  if (part.type === "image" && part.source) {
    return <InlineImage source={part.source} />;
  }

  return null;
}

function InlineImage({ source }: { source: NonNullable<ContentPart["source"]> }) {
  const [expanded, setExpanded] = useState(false);
  const dataUrl = `data:${source.media_type};base64,${source.base64}`;

  return (
    <>
      <img
        src={dataUrl}
        alt="Embedded image"
        className="my-2 max-w-full max-h-80 rounded-lg border border-card cursor-pointer hover:border-dimmed transition-colors"
        onClick={() => setExpanded(true)}
      />
      {expanded && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 cursor-pointer"
          onClick={() => setExpanded(false)}
        >
          <img
            src={dataUrl}
            alt="Expanded image"
            className="max-w-[90vw] max-h-[90vh] rounded-lg"
          />
        </div>
      )}
    </>
  );
}
