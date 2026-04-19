import {
  Anchor,
  Bot,
  ChevronLeft,
  ChevronRight,
  Info,
  type LucideIcon,
  Package,
  RefreshCw,
  Terminal,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useExtensionsClient } from "../../app";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import type { ExtensionSyncTarget } from "../../types";
import { SEARCH_DEBOUNCE_MS } from "../../constants";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { EmptyState } from "../ui/empty-state";
import { ErrorBanner } from "../ui/error-banner";
import { LoadingState } from "../ui/loading-state";
import { Tooltip } from "../ui/tooltip";
import {
  LocalExtensionDetailView,
  type LocalExtensionKind,
} from "./extensions/extension-detail-view";
import { UninstallExtensionDialog } from "./extensions/uninstall-extension-dialog";
import { SourceBadge, TagList, ToolList } from "./source-badges";
import { NoResultsState, ResultCount, SearchBar, SourceFilterBar } from "./result-shared";

const DEFAULT_PAGE_SIZE = 50;
const PAGE_SIZE_OPTIONS = [25, 50, 100];

interface LocalItem {
  name: string;
  description: string;
  topics: string[];
  allowed_tools?: string[];
  installed_in: string[];
}

interface KindConfig {
  key: LocalExtensionKind;
  apiKey: "skills" | "subagents" | "commands" | "plugins";
  label: string;
  pluralLabel: string;
  icon: LucideIcon;
  accent: string;
  accentText: string;
  description: string;
  canEdit: boolean;
  contentLabel: string;
  contentPlaceholder: string;
}

const KIND_CONFIGS: Record<LocalExtensionKind, KindConfig> = {
  skill: {
    key: "skill",
    apiKey: "skills",
    label: "Skill",
    pluralLabel: "Skills",
    icon: Package,
    accent: "bg-accent-teal-subtle",
    accentText: "text-accent-teal",
    description:
      "Reusable guides that teach your agent how to do a specific job, like writing ads or reviewing code.",
    canEdit: true,
    contentLabel: "SKILL.md content",
    contentPlaceholder:
      "---\ndescription: What this skill does\nallowed-tools: Read, Edit, Bash\ntags: [development, automation]\n---\n\n# Instructions\n\n...",
  },
  subagent: {
    key: "subagent",
    apiKey: "subagents",
    label: "Subagent",
    pluralLabel: "Subagents",
    icon: Bot,
    accent: "bg-accent-violet-subtle",
    accentText: "text-accent-violet",
    description:
      "A helper your agent can hand a small job off to, so the main conversation stays focused.",
    canEdit: true,
    contentLabel: "Subagent markdown",
    contentPlaceholder:
      "---\nname: my-subagent\ndescription: What this subagent does\n---\n\nInstructions...",
  },
  command: {
    key: "command",
    apiKey: "commands",
    label: "Command",
    pluralLabel: "Commands",
    icon: Terminal,
    accent: "bg-accent-cyan-subtle",
    accentText: "text-accent-cyan",
    description:
      "Shortcuts you can type with a slash to kick off a common task, like /review or /ship.",
    canEdit: true,
    contentLabel: "Command markdown",
    contentPlaceholder:
      "---\nname: my-command\ndescription: Short description shown in the slash menu\n---\n\nCommand body...",
  },
  plugin: {
    key: "plugin",
    apiKey: "plugins",
    label: "Plugin",
    pluralLabel: "Plugins",
    icon: Anchor,
    accent: "bg-accent-indigo-subtle",
    accentText: "text-accent-indigo",
    description:
      "A bundle that installs a set of skills, commands, and subagents together. Add new ones from Explore.",
    canEdit: false,
    contentLabel: "plugin.json",
    contentPlaceholder: "",
  },
};

const KIND_ORDER: LocalExtensionKind[] = ["skill", "subagent", "command", "plugin"];

interface LocalExtensionsTabProps {
  refreshTrigger?: number;
}

export function LocalExtensionsTab({ refreshTrigger = 0 }: LocalExtensionsTabProps = {}) {
  const client = useExtensionsClient();
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [kind, setKind] = useState<LocalExtensionKind>("skill");
  const [detailName, setDetailName] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [syncTargetsByType, setSyncTargetsByType] = useState<
    Record<string, ExtensionSyncTarget[]>
  >({});

  useEffect(() => {
    setDetailName(null);
  }, [kind]);

  const config = KIND_CONFIGS[kind];
  const syncTargets = syncTargetsByType[kind] ?? [];
  const combinedRefresh = refreshTrigger + refreshTick;

  useEffect(() => {
    if (combinedRefresh > 0) client.syncTargets.invalidate();
    client.syncTargets
      .get()
      .then((targets) => setSyncTargetsByType(targets))
      .catch(() => {});
  }, [client, combinedRefresh]);

  if (detailName) {
    return (
      <LocalExtensionDetailView
        extensionType={kind}
        name={detailName}
        syncTargets={syncTargets}
        onBack={() => setDetailName(null)}
        onUninstalled={() => setDetailName(null)}
      />
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-start justify-between gap-3 mb-5">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`p-2 rounded-lg ${config.accent}`}>
            <config.icon className={`w-5 h-5 ${config.accentText}`} />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-primary">Local</h2>
            <p className="text-sm text-secondary">
              Manage and sync installed extensions across agent interfaces
            </p>
          </div>
        </div>
        <Tooltip text="Refresh list">
          <button
            onClick={() => setRefreshTick((n) => n + 1)}
            className="shrink-0 p-2 text-muted hover:text-primary bg-control hover:bg-control-hover border border-card rounded-md transition"
            aria-label="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </Tooltip>
      </div>

      <div className="flex rounded-lg bg-control p-0.5 mb-5 w-fit" role="tablist">
        {KIND_ORDER.map((k) => {
          const c = KIND_CONFIGS[k];
          const Icon = c.icon;
          const active = kind === k;
          return (
            <button
              key={k}
              role="tab"
              aria-selected={active}
              onClick={() => setKind(k)}
              className={`flex items-center gap-1.5 px-4 py-1.5 text-xs rounded-md transition ${
                active
                  ? "bg-panel text-primary font-semibold shadow-sm"
                  : "text-muted hover:text-secondary"
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${active ? c.accentText : ""}`} />
              {c.pluralLabel}
            </button>
          );
        })}
      </div>

      <LocalKindPanel
        kind={kind}
        config={config}
        refreshTrigger={combinedRefresh}
        onOpenDetail={(name) => setDetailName(name)}
        guardAction={guardAction}
      />

      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

interface LocalKindPanelProps {
  kind: LocalExtensionKind;
  config: KindConfig;
  refreshTrigger: number;
  onOpenDetail: (name: string) => void;
  guardAction: (fn: () => void | Promise<void>) => void;
}

function LocalKindPanel({
  kind,
  config,
  refreshTrigger,
  onOpenDetail,
  guardAction,
}: LocalKindPanelProps) {
  const client = useExtensionsClient();
  const api = client[config.apiKey];
  const [items, setItems] = useState<LocalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredItems, setFilteredItems] = useState<LocalItem[]>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<LocalItem | null>(null);
  const [deleteInFlight, setDeleteInFlight] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [total, setTotal] = useState(0);

  const fetchItems = useCallback(
    async (forceRefresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.list({
          page,
          pageSize,
          refresh: forceRefresh || undefined,
        });
        const newItems = (data.items ?? []) as unknown as LocalItem[];
        setItems(newItems);
        setFilteredItems(newItems);
        setTotal(data.total ?? newItems.length);
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    },
    [api, page, pageSize],
  );

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  useEffect(() => {
    if (refreshTrigger === 0) return;
    fetchItems();
  }, [refreshTrigger, fetchItems]);

  useEffect(() => {
    let result = items;
    if (sourceFilter) {
      result = result.filter((s) => s.installed_in.includes(sourceFilter));
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q),
      );
    }
    setFilteredItems(result);
  }, [items, sourceFilter, searchQuery]);

  useEffect(() => {
    setSearchQuery("");
    setSourceFilter(null);
    setPage(1);
  }, [kind]);

  const handleSearchChange = useCallback(
    (query: string) => {
      setSearchQuery(query);
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
      if (!query.trim()) {
        fetchItems();
        return;
      }
      searchTimerRef.current = setTimeout(async () => {
        try {
          const data = await api.list({ search: query, page: 1, pageSize });
          const newItems = (data.items ?? []) as unknown as LocalItem[];
          setItems(newItems);
          setTotal(data.total ?? newItems.length);
        } catch {
          /* fallback to local filter */
        }
      }, SEARCH_DEBOUNCE_MS);
    },
    [api, fetchItems, pageSize],
  );

  const handleDelete = useCallback(
    async (item: LocalItem) => {
      setError(null);
      setDeleteInFlight(true);
      try {
        await api.uninstall(item.name);
        setDeleteTarget(null);
        await fetchItems();
      } catch (err) {
        setError(String(err));
        setDeleteTarget(null);
      } finally {
        setDeleteInFlight(false);
      }
    },
    [api, fetchItems],
  );

  const availableSourceTypes = useMemo(
    () => Array.from(new Set(items.flatMap((s) => s.installed_in))),
    [items],
  );

  return (
    <>
      <div className="mb-5 px-4 py-3.5 rounded-lg border border-teal-300 dark:border-teal-800/40 bg-teal-50 dark:bg-teal-950/20 overflow-hidden">
        <div className="flex items-center gap-3">
          <div className="shrink-0 p-2 rounded-lg bg-teal-100 dark:bg-teal-500/15 border border-teal-200 dark:border-teal-500/20">
            <Info className="w-4 h-4 text-teal-600 dark:text-teal-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-base font-bold text-primary">{config.pluralLabel}</p>
            <p className="text-sm text-secondary mt-0.5">{config.description}</p>
          </div>
        </div>
      </div>

      <SourceFilterBar
        items={availableSourceTypes}
        activeKey={sourceFilter}
        onSelect={setSourceFilter}
        totalCount={items.length}
        countByKey={(key) => items.filter((s) => s.installed_in.includes(key)).length}
      />

      <SearchBar value={searchQuery} onChange={handleSearchChange} />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {loading && items.length === 0 && <LoadingState label={`Loading ${config.pluralLabel.toLowerCase()}...`} />}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          icon={config.icon}
          title={`No ${config.pluralLabel.toLowerCase()} installed`}
          subtitle="Install one from the Explore tab to get started."
        />
      )}

      {!loading && items.length > 0 && filteredItems.length === 0 && <NoResultsState />}

      {filteredItems.length > 0 && (
        <div className="space-y-2">
          <ResultCount filtered={filteredItems.length} total={total} />
          {filteredItems.map((item) => (
            <LocalExtensionCard
              key={item.name}
              item={item}
              config={config}
              onDelete={() => guardAction(() => setDeleteTarget(item))}
              onActivate={() => onOpenDetail(item.name)}
            />
          ))}
          <PaginationBar
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setPage(1);
            }}
          />
        </div>
      )}

      {deleteTarget && (
        <UninstallExtensionDialog
          entityLabel={config.label.toLowerCase()}
          name={deleteTarget.name}
          installedIn={deleteTarget.installed_in}
          loading={deleteInFlight}
          onConfirm={() => handleDelete(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </>
  );
}

interface LocalExtensionCardProps {
  item: LocalItem;
  config: KindConfig;
  onDelete: () => void;
  onActivate: () => void;
}

function LocalExtensionCard({
  item,
  config,
  onDelete,
  onActivate,
}: LocalExtensionCardProps) {
  const tags = item.topics ?? [];
  const allowedTools = item.allowed_tools ?? [];

  return (
    <div className="border border-card rounded-lg bg-panel hover:bg-control/80 transition">
      <div className="flex items-start">
        <button
          onClick={onActivate}
          className="flex-1 text-left px-4 py-3 flex items-start gap-3 min-w-0"
        >
          <div className={`shrink-0 mt-0.5 p-1.5 rounded-md ${config.accent}`}>
            <config.icon className={`w-4 h-4 ${config.accentText}`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-base font-bold text-primary">{item.name}</span>
              {item.installed_in.map((agent) => (
                <SourceBadge key={agent} sourceType={agent} sourcePath="" />
              ))}
            </div>
            <p className="text-sm text-secondary mt-1 line-clamp-2">
              {item.description || "No description"}
            </p>
            <TagList tags={tags} />
            {allowedTools.length > 0 && <ToolList tools={allowedTools} />}
          </div>
        </button>
        <div className="flex items-center gap-1.5 px-3 py-3 shrink-0">
          <Tooltip text={`Delete ${config.label.toLowerCase()}`}>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="p-2 text-dimmed hover:text-red-600 dark:hover:text-red-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 rounded-md transition"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}

function PaginationBar({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= PAGE_SIZE_OPTIONS[0]) return null;

  return (
    <div className="flex items-center justify-between pt-4 border-t border-default text-xs text-dimmed">
      <div className="flex items-center gap-2">
        <span>Show</span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="bg-control border border-card rounded px-1.5 py-0.5 text-secondary text-xs"
        >
          {PAGE_SIZE_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        <span>per page</span>
      </div>
      <div className="flex items-center gap-2">
        <span>
          {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}
        </span>
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="p-1 rounded hover:bg-control-hover disabled:opacity-30 disabled:cursor-not-allowed transition"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="p-1 rounded hover:bg-control-hover disabled:opacity-30 disabled:cursor-not-allowed transition"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
