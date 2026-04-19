import { Check, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { TOGGLE_ACTIVE, TOGGLE_BUTTON_BASE, TOGGLE_CONTAINER, TOGGLE_INACTIVE } from "../../../styles";
import { CopyButton } from "../../ui/copy-button";
import { MarkdownRenderer } from "../../ui/markdown-renderer";

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
  itemName?: string;
  itemDescription?: string;
  /** Controlled preview/code mode; lifted so the parent can render a sibling TOC. */
  mode: ContentMode;
  onModeChange: (mode: ContentMode) => void;
  /** When provided, code mode becomes editable with a Save button that
   *  invokes this callback with the new text.
   */
  onSave?: (nextContent: string) => Promise<void>;
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

export type ContentMode = "preview" | "code";

export function ExtensionDetailContent({
  content,
  itemName,
  itemDescription,
  mode,
  onModeChange,
  onSave,
}: ExtensionDetailContentProps) {
  const contentMode = mode;
  const setContentMode = onModeChange;
  const { data: frontmatter, body } = useMemo(() => parseFrontmatter(content), [content]);

  const editable = Boolean(onSave);
  const [draft, setDraft] = useState(content);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Reset draft whenever the underlying file changes (e.g., user picked a
  // different file in the sidebar).
  useEffect(() => {
    setDraft(content);
    setSaveError(null);
  }, [content]);

  const dirty = editable && draft !== content;

  const displayName = frontmatter.name || itemName;
  const displayDescription = frontmatter.description || itemDescription;

  async function handleSave() {
    if (!onSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(draft);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-center justify-between px-4 py-2.5 gap-3">
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
        <div className="flex items-center gap-2">
          {editable && contentMode === "code" && (
            <>
              {dirty && !saving && (
                <button
                  onClick={() => setDraft(content)}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs text-muted hover:text-secondary border border-card hover:border-hover rounded transition"
                >
                  <RotateCcw className="w-3 h-3" />
                  Revert
                </button>
              )}
              <button
                onClick={handleSave}
                disabled={!dirty || saving}
                className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-md transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Check className="w-3 h-3" />
                )}
                Save
              </button>
            </>
          )}
          <CopyButton text={editable ? draft : content} />
        </div>
      </div>

      {saveError && (
        <div className="mx-4 mb-2 px-3 py-2 rounded-md bg-rose-50 dark:bg-rose-950/20 text-xs text-rose-700 dark:text-rose-300">
          Failed to save: {saveError}
        </div>
      )}

      <div className="px-6 lg:px-8 pb-8">
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
        ) : editable ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            className="w-full min-h-[420px] font-mono text-sm text-secondary bg-control/30 border border-card rounded-lg px-4 py-3 outline-none focus:ring-1 focus:ring-teal-500/30 focus:border-accent-teal-focus resize-y"
          />
        ) : (
          <pre className="font-mono text-sm text-secondary whitespace-pre-wrap break-words leading-relaxed">
            {content}
          </pre>
        )}
      </div>
    </div>
  );
}
