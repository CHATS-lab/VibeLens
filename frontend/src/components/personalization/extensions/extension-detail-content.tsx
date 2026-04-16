import { useMemo, useState } from "react";
import { TOGGLE_ACTIVE, TOGGLE_BUTTON_BASE, TOGGLE_CONTAINER, TOGGLE_INACTIVE } from "../../styles";
import { CopyButton } from "../copy-button";
import { MarkdownRenderer } from "../markdown-renderer";

export interface TocEntry {
  level: number;
  text: string;
  slug: string;
}

interface FrontmatterData {
  name?: string;
  description?: string;
}

interface ExtensionDetailContentProps {
  content: string;
  tocEntries: TocEntry[];
  itemName?: string;
  itemDescription?: string;
}

/** Parse YAML frontmatter, extracting name and description fields. */
export function parseFrontmatter(text: string): { data: FrontmatterData; body: string } {
  const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/);
  if (!match) return { data: {}, body: text };

  const yaml = match[1];
  const body = match[2].trimStart();
  const data: FrontmatterData = {};

  const nameMatch = yaml.match(/^name:\s*(.+)$/m);
  if (nameMatch) data.name = nameMatch[1].trim().replace(/^["']|["']$/g, "");

  const descMatch = yaml.match(/^description:\s*(.+)$/m);
  if (descMatch) data.description = descMatch[1].trim().replace(/^["']|["']$/g, "");

  return { data, body };
}

/** Strip YAML frontmatter (--- ... ---) from markdown content. */
export function stripFrontmatter(text: string): string {
  return parseFrontmatter(text).body;
}

type ContentMode = "preview" | "code";

export function ExtensionDetailContent({
  content,
  tocEntries,
  itemName,
  itemDescription,
}: ExtensionDetailContentProps) {
  const [contentMode, setContentMode] = useState<ContentMode>("preview");
  const { data: frontmatter, body } = useMemo(() => parseFrontmatter(content), [content]);

  const displayName = frontmatter.name || itemName;
  const displayDescription = frontmatter.description || itemDescription;

  return (
    <div className="flex gap-6">
      {/* Main content panel */}
      <div className="flex-1 min-w-0 border border-card rounded-xl bg-panel overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-5 py-2.5 border-b border-card bg-control/30">
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
        <div className="p-6 lg:p-8">
          {contentMode === "preview" ? (
            <>
              {displayName && (
                <div className="mb-6 pb-5 border-b border-card">
                  <h1 className="text-2xl font-bold text-primary leading-tight">
                    {displayName}
                  </h1>
                  {displayDescription && (
                    <p className="text-[15px] text-secondary mt-2.5 leading-relaxed">
                      {displayDescription}
                    </p>
                  )}
                </div>
              )}
              <MarkdownRenderer content={body} variant="document" />
            </>
          ) : (
            <pre className="font-mono text-sm text-secondary whitespace-pre-wrap break-words leading-relaxed">
              {content}
            </pre>
          )}
        </div>
      </div>

      {/* TOC sidebar — only in preview mode when enough headings exist */}
      {contentMode === "preview" && tocEntries.length > 2 && (
        <nav className="hidden lg:block w-56 shrink-0 sticky top-6 self-start">
          <h3 className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-3">
            On this page
          </h3>
          <ul className="space-y-0.5 border-l border-card">
            {tocEntries.map((entry) => (
              <li key={entry.slug}>
                <a
                  href={`#${entry.slug}`}
                  className="block text-xs text-muted hover:text-primary transition truncate py-1"
                  style={{ paddingLeft: `${(entry.level - 1) * 10 + 12}px` }}
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
