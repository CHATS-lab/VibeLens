import { useState } from "react";
import { TOGGLE_ACTIVE, TOGGLE_BUTTON_BASE, TOGGLE_CONTAINER, TOGGLE_INACTIVE } from "../../styles";
import { CopyButton } from "../copy-button";
import { MarkdownRenderer } from "../markdown-renderer";

export interface TocEntry {
  level: number;
  text: string;
  slug: string;
}

interface CatalogDetailContentProps {
  content: string;
  tocEntries: TocEntry[];
}

type ContentMode = "preview" | "code";

export function CatalogDetailContent({ content, tocEntries }: CatalogDetailContentProps) {
  const [contentMode, setContentMode] = useState<ContentMode>("preview");

  return (
    <div className="flex gap-6">
      {/* Main content panel */}
      <div className="flex-1 min-w-0 border border-card rounded-lg bg-panel overflow-auto">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-card">
          <div className={`${TOGGLE_CONTAINER} w-36`}>
            <button
              className={`${TOGGLE_BUTTON_BASE} ${contentMode === "preview" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE}`}
              onClick={() => setContentMode("preview")}
            >
              Preview
            </button>
            <button
              className={`${TOGGLE_BUTTON_BASE} ${contentMode === "code" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE}`}
              onClick={() => setContentMode("code")}
            >
              Code
            </button>
          </div>
          <CopyButton text={content} />
        </div>

        {/* Content body */}
        <div className="p-6">
          {contentMode === "preview" ? (
            <MarkdownRenderer content={content} />
          ) : (
            <pre className="font-mono text-sm text-secondary whitespace-pre-wrap break-words">{content}</pre>
          )}
        </div>
      </div>

      {/* TOC sidebar — only in preview mode when enough headings exist */}
      {contentMode === "preview" && tocEntries.length > 2 && (
        <nav className="hidden lg:block w-56 shrink-0 sticky top-6 self-start">
          <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">On this page</h3>
          <ul className="space-y-1.5">
            {tocEntries.map((entry) => (
              <li key={entry.slug} style={{ paddingLeft: `${(entry.level - 1) * 12}px` }}>
                <a
                  href={`#${entry.slug}`}
                  className="text-xs text-muted hover:text-secondary transition block truncate"
                >
                  {entry.text}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </div>
  );
}
