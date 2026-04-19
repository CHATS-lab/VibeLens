import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Tooltip } from "../../ui/tooltip";
import type { ExtensionTreeEntry } from "../../../types";

interface ExtensionFileTreeProps {
  entries: ExtensionTreeEntry[];
  selected: string | null;
  onSelect: (path: string) => void;
  rootLabel: string;
  onBack?: () => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

type TreeNode = {
  name: string;
  path: string;
  kind: "file" | "dir";
  children: TreeNode[];
};

/** Sort helper: dirs first, then files, alphabetical within each group. */
function sortChildren(nodes: TreeNode[]): TreeNode[] {
  return [...nodes].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

/** Build a nested tree from the flat path list returned by the backend. */
function buildTree(entries: ExtensionTreeEntry[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", kind: "dir", children: [] };
  const lookup = new Map<string, TreeNode>();
  lookup.set("", root);

  // Pre-seed any dir entries so their metadata is preserved.
  for (const entry of entries) {
    if (!entry.path) continue;
    const segments = entry.path.split("/");
    let parentPath = "";
    segments.forEach((name, idx) => {
      const isLast = idx === segments.length - 1;
      const path = segments.slice(0, idx + 1).join("/");
      let node = lookup.get(path);
      if (!node) {
        node = {
          name,
          path,
          kind: isLast ? entry.kind : "dir",
          children: [],
        };
        lookup.set(path, node);
        lookup.get(parentPath)?.children.push(node);
      }
      parentPath = path;
    });
  }

  const normalize = (node: TreeNode): TreeNode => {
    if (node.kind === "dir") {
      node.children = sortChildren(node.children.map(normalize));
    }
    return node;
  };
  return sortChildren(root.children.map(normalize));
}

export function ExtensionFileTree({
  entries,
  selected,
  onSelect,
  rootLabel,
  onBack,
  collapsed = false,
  onToggleCollapsed,
}: ExtensionFileTreeProps) {
  const [filter, setFilter] = useState("");
  const [collapsedDirs, setCollapsedDirs] = useState<Set<string>>(() => new Set());

  const fileEntries = useMemo(
    () => entries.filter((e) => e.kind === "file"),
    [entries],
  );
  const tree = useMemo(() => buildTree(entries), [entries]);

  const filteredFiles = useMemo(() => {
    if (!filter.trim()) return null;
    const q = filter.toLowerCase();
    return fileEntries.filter((e) => e.path.toLowerCase().includes(q));
  }, [fileEntries, filter]);

  const toggleDir = (path: string) => {
    setCollapsedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  if (collapsed) {
    return (
      <aside className="w-12 shrink-0 flex flex-col items-center py-3 gap-3 border-r border-card">
        <Tooltip text="Show files">
          <button
            onClick={onToggleCollapsed}
            className="p-1.5 text-muted hover:text-primary hover:bg-control rounded-md transition"
            aria-label="Expand file tree"
          >
            <PanelLeftOpen className="w-4 h-4" />
          </button>
        </Tooltip>
        <span className="text-[10px] text-muted px-1.5 py-0.5 rounded bg-control tabular-nums font-mono">
          {fileEntries.length}
        </span>
      </aside>
    );
  }

  return (
    <aside className="w-52 shrink-0 flex flex-col min-h-0 border-r border-card">
      <div className="flex items-center gap-2 px-3 py-3">
        {onBack && (
          <button
            onClick={onBack}
            className="p-1 text-muted hover:text-primary rounded transition"
            aria-label="Back"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
        <span className="font-mono text-sm font-bold text-primary truncate flex-1">
          {rootLabel}
        </span>
        <span className="text-[11px] text-muted px-1.5 py-0.5 rounded bg-control tabular-nums">
          {fileEntries.length}
        </span>
        {onToggleCollapsed && (
          <Tooltip text="Hide files">
            <button
              onClick={onToggleCollapsed}
              className="p-1 text-muted hover:text-primary hover:bg-control rounded transition"
              aria-label="Collapse file tree"
            >
              <PanelLeftClose className="w-3.5 h-3.5" />
            </button>
          </Tooltip>
        )}
      </div>
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted pointer-events-none" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter files..."
            className="w-full pl-8 pr-2 py-1.5 text-xs bg-control border border-card rounded text-primary placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-teal-500/30 focus:border-accent-teal-focus transition"
          />
        </div>
      </div>
      <ul className="flex-1 overflow-y-auto py-1 pr-1">
        {filteredFiles !== null
          ? (
            filteredFiles.length === 0 ? (
              <li className="px-4 py-3 text-[11px] text-muted italic">No files match.</li>
            ) : (
              filteredFiles.map((entry) => (
                <TreeFile
                  key={entry.path}
                  path={entry.path}
                  label={entry.path}
                  depth={0}
                  selected={entry.path === selected}
                  onSelect={onSelect}
                />
              ))
            )
          )
          : tree.length === 0 ? (
            <li className="px-4 py-3 text-[11px] text-muted italic">Empty.</li>
          ) : (
            tree.map((node) => (
              <TreeRow
                key={node.path}
                node={node}
                depth={0}
                selected={selected}
                collapsedDirs={collapsedDirs}
                onToggleDir={toggleDir}
                onSelect={onSelect}
              />
            ))
          )}
      </ul>
    </aside>
  );
}

interface TreeRowProps {
  node: TreeNode;
  depth: number;
  selected: string | null;
  collapsedDirs: Set<string>;
  onToggleDir: (path: string) => void;
  onSelect: (path: string) => void;
}

function TreeRow({
  node,
  depth,
  selected,
  collapsedDirs,
  onToggleDir,
  onSelect,
}: TreeRowProps) {
  if (node.kind === "file") {
    return (
      <TreeFile
        path={node.path}
        label={node.name}
        depth={depth}
        selected={node.path === selected}
        onSelect={onSelect}
      />
    );
  }

  const open = !collapsedDirs.has(node.path);
  return (
    <>
      <li>
        <Tooltip text={node.path}>
          <button
            onClick={() => onToggleDir(node.path)}
            className="w-full flex items-center gap-1 py-0.5 text-left text-[11px] text-secondary hover:bg-control/60 rounded transition"
            style={{ paddingLeft: `${8 + depth * 12}px`, paddingRight: 8 }}
          >
            {open ? (
              <ChevronDown className="w-3 h-3 shrink-0 text-muted" />
            ) : (
              <ChevronRight className="w-3 h-3 shrink-0 text-muted" />
            )}
            {open ? (
              <FolderOpen className="w-3.5 h-3.5 shrink-0 text-accent-amber" />
            ) : (
              <Folder className="w-3.5 h-3.5 shrink-0 text-accent-amber" />
            )}
            <span className="truncate flex-1 font-medium">{node.name}</span>
          </button>
        </Tooltip>
      </li>
      {open &&
        node.children.map((child) => (
          <TreeRow
            key={child.path}
            node={child}
            depth={depth + 1}
            selected={selected}
            collapsedDirs={collapsedDirs}
            onToggleDir={onToggleDir}
            onSelect={onSelect}
          />
        ))}
    </>
  );
}

interface TreeFileProps {
  path: string;
  label: string;
  depth: number;
  selected: boolean;
  onSelect: (path: string) => void;
}

function TreeFile({ path, label, depth, selected, onSelect }: TreeFileProps) {
  return (
    <li>
      <Tooltip text={path}>
        <button
          onClick={() => onSelect(path)}
          className={`w-full flex items-center gap-1.5 py-0.5 text-left font-mono text-[11px] rounded transition ${
            selected
              ? "bg-accent-amber-subtle text-amber-700 dark:text-amber-300"
              : "text-secondary hover:bg-control/60"
          }`}
          style={{ paddingLeft: `${20 + depth * 12}px`, paddingRight: 8 }}
        >
          <FileText className="w-3 h-3 shrink-0 text-muted" />
          <span className="truncate flex-1">{label}</span>
        </button>
      </Tooltip>
    </li>
  );
}
