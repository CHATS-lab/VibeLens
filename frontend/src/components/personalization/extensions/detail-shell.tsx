import { ArrowLeft, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../../app";
import type { ExtensionTreeEntry } from "../../../types";
import {
  ExtensionDetailContent,
  stripFrontmatter,
  type ContentMode,
  type TocEntry,
} from "./extension-detail-content";
import { ExtensionFileTree } from "./extension-file-tree";

const PRIMARY_FILENAMES: Record<string, string[]> = {
  skill: ["SKILL.md"],
  plugin: [".claude-plugin/plugin.json", "plugin.json"],
  subagent: [],
  command: [],
};

function extractTocEntries(markdown: string): TocEntry[] {
  const regex = /^(#{1,3})\s+(.+)$/gm;
  const entries: TocEntry[] = [];
  let match: RegExpExecArray | null;
  while ((match = regex.exec(markdown)) !== null) {
    const level = match[1].length;
    const text = match[2].trim();
    const slug = text
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/\s+/g, "-");
    entries.push({ level, text, slug });
  }
  return entries;
}

/** Pick the "primary" file to open by default, based on type conventions. */
export function pickPrimaryPath(
  entries: ExtensionTreeEntry[],
  extensionType: string,
): string | null {
  if (entries.length === 0) return null;
  const files = entries.filter((e) => e.kind === "file");
  if (files.length === 0) return null;
  const preferred = PRIMARY_FILENAMES[extensionType] ?? [];
  for (const candidate of preferred) {
    const hit = files.find((f) => f.path === candidate || f.path.endsWith(`/${candidate}`));
    if (hit) return hit.path;
  }
  const md = files.find((f) => f.path.toLowerCase().endsWith(".md"));
  return md ? md.path : files[0].path;
}

/** Common detail-page layout: header card + file tree sidebar + content pane. */
interface DetailShellProps {
  headerContent: React.ReactNode;
  metadataContent: React.ReactNode;
  onBack: () => void;
  entries: ExtensionTreeEntry[];
  selectedPath: string | null;
  onSelectPath: (path: string) => void;
  rootLabel: string;
  fileContent: string | null;
  fileError: string | null;
  loading: boolean;
  backLabel?: string;
  initialCollapsed?: boolean;
  onSaveContent?: (path: string, content: string) => Promise<void>;
}

export function DetailShell({
  headerContent,
  metadataContent,
  onBack,
  entries,
  selectedPath,
  onSelectPath,
  rootLabel,
  fileContent,
  fileError,
  loading,
  backLabel = "Back",
  initialCollapsed = false,
  onSaveContent,
}: DetailShellProps) {
  const { setSidebarOpen } = useAppContext();
  useEffect(() => {
    setSidebarOpen(false);
    return () => setSidebarOpen(true);
  }, [setSidebarOpen]);

  const tocEntries = useMemo(
    () => (fileContent ? extractTocEntries(stripFrontmatter(fileContent)) : []),
    [fileContent],
  );
  const hasTree = entries.some((e) => e.kind === "file");
  const [treeCollapsed, setTreeCollapsed] = useState(initialCollapsed);
  const [contentMode, setContentMode] = useState<ContentMode>("preview");
  const showToc = contentMode === "preview" && tocEntries.length > 2;

  return (
    <div className="pb-6">
      <button
        onClick={onBack}
        className="sticky top-0 z-20 left-0 w-fit ml-3 mt-3 flex items-center gap-1.5 px-2 py-1 text-sm text-muted hover:text-secondary bg-canvas/95 backdrop-blur-sm rounded transition"
      >
        <ArrowLeft className="w-4 h-4" />
        {backLabel}
      </button>

      <div className="max-w-[1400px] mx-auto px-6 mt-3">
        <div className="border border-card rounded-xl bg-panel overflow-hidden mb-6">
          {headerContent}
          {metadataContent}
        </div>

        <div className="flex gap-6 items-start">
          <div className="flex-1 min-w-0 flex min-h-[420px] border border-card rounded-xl bg-panel overflow-hidden">
            {hasTree && (
              <ExtensionFileTree
                entries={entries}
                selected={selectedPath}
                onSelect={onSelectPath}
                rootLabel={rootLabel}
                collapsed={treeCollapsed}
                onToggleCollapsed={() => setTreeCollapsed((v) => !v)}
              />
            )}
            <div className="flex-1 min-w-0 overflow-y-auto">
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted py-8 justify-center">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading content...
                </div>
              ) : fileError ? (
                <div className="mx-4 mt-4 flex items-start gap-2 px-4 py-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30">
                  <p className="text-sm text-red-700 dark:text-red-300">{fileError}</p>
                </div>
              ) : fileContent !== null ? (
                <ExtensionDetailContent
                  content={fileContent}
                  itemName={selectedPath ?? undefined}
                  mode={contentMode}
                  onModeChange={setContentMode}
                  onSave={
                    onSaveContent && selectedPath
                      ? (text) => onSaveContent(selectedPath, text)
                      : undefined
                  }
                />
              ) : (
                <p className="text-center text-sm text-muted py-8">
                  Select a file from the left to preview its contents.
                </p>
              )}
            </div>
          </div>

          {showToc && (
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
      </div>
    </div>
  );
}
