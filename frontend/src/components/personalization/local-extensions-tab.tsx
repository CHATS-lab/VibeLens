import { Check, ChevronLeft, ChevronRight, Code2, Info, Package, Pencil, Plus, RefreshCw, Share2, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useExtensionsClient } from "../../app";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import type { ExtensionSyncTarget, Skill } from "../../types";
import { SEARCH_DEBOUNCE_MS } from "../../constants";
import { ConfirmDialog } from "../confirm-dialog";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { EditorDialog } from "./editor-dialog";
import { EmptyState } from "../empty-state";
import { ErrorBanner } from "../error-banner";
import { LoadingState } from "../loading-state";
import { MarkdownRenderer } from "../markdown-renderer";
import { Modal, ModalHeader, ModalBody } from "../modal";
import { Tooltip } from "../tooltip";
import { SourceBadge, TagList, TagPill, ToolBadge, ToolList } from "./badges";
import { SOURCE_LABELS } from "./constants";
import {
  NoResultsState,
  ResultCount,
  SearchBar,
  SourceFilterBar,
} from "./shared";

const DEFAULT_PAGE_SIZE = 50;
const PAGE_SIZE_OPTIONS = [25, 50, 100];

interface EditorState {
  open: boolean;
  mode: "create" | "edit";
  name: string;
  content: string;
}

const EDITOR_CLOSED: EditorState = { open: false, mode: "create", name: "", content: "" };

export function LocalExtensionsTab({ refreshTrigger = 0 }: { refreshTrigger?: number } = {}) {
  const client = useExtensionsClient();
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredSkills, setFilteredSkills] = useState<Skill[]>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [editorState, setEditorState] = useState<EditorState>(EDITOR_CLOSED);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null);
  const [detailSkill, setDetailSkill] = useState<Skill | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [syncTargets, setSkillSyncTargets] = useState<ExtensionSyncTarget[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [totalSkills, setTotalSkills] = useState(0);

  const fetchSkills = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await client.skills.list({
        page,
        pageSize,
        refresh: forceRefresh || undefined,
      });
      const items = (data.items ?? []) as unknown as Skill[];
      setSkills(items);
      setFilteredSkills(items);
      setTotalSkills(data.total ?? items.length);
      if (data.sync_targets) setSkillSyncTargets(data.sync_targets);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [client, page, pageSize]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  // External refresh trigger (e.g., after installing a skill from an analysis view).
  useEffect(() => {
    if (refreshTrigger === 0) return;
    fetchSkills();
  }, [refreshTrigger, fetchSkills]);

  // Apply source filter + search query
  useEffect(() => {
    let result = skills;
    if (sourceFilter) {
      result = result.filter((s) => s.installed_in.includes(sourceFilter));
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q),
      );
    }
    setFilteredSkills(result);
  }, [skills, sourceFilter, searchQuery]);

  const handleSearchChange = useCallback(
    (query: string) => {
      setSearchQuery(query);
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);

      // When query is cleared, refetch full list from server
      if (!query.trim()) {
        fetchSkills();
        return;
      }

      searchTimerRef.current = setTimeout(async () => {
        try {
          const data = await client.skills.list({ search: query, page: 1, pageSize });
          const items = (data.items ?? []) as unknown as Skill[];
          setSkills(items);
          setTotalSkills(data.total ?? items.length);
          if (data.sync_targets) setSkillSyncTargets(data.sync_targets);
        } catch {
          /* fallback to local filter */
        }
      }, SEARCH_DEBOUNCE_MS);
    },
    [client, fetchSkills, pageSize],
  );

  const handleSave = useCallback(
    async (name: string, content: string) => {
      setSaving(true);
      setError(null);
      try {
        const isCreate = editorState.mode === "create";
        let installedIn: string[] = [];
        if (isCreate) {
          const result = await client.skills.install(name, content, []);
          const skill = result as unknown as { installed_in?: string[] };
          installedIn = skill.installed_in ?? [];
        } else {
          const result = await client.skills.modify(name, content);
          const skill = result as unknown as { installed_in?: string[] };
          installedIn = skill.installed_in ?? [];
        }
        setEditorState(EDITOR_CLOSED);

        // Auto-sync to all previously synced agent interfaces after edit
        if (editorState.mode === "edit" && installedIn.length > 0) {
          client.skills.syncToAgents(name, installedIn).catch(() => {});
        }

        await fetchSkills();
      } catch (err) {
        setError(String(err));
      } finally {
        setSaving(false);
      }
    },
    [client, editorState.mode, fetchSkills],
  );

  const handleDelete = useCallback(
    async (skill: Skill) => {
      setError(null);
      try {
        await client.skills.uninstall(skill.name);
        setDeleteTarget(null);
        await fetchSkills();
      } catch (err) {
        setError(String(err));
        setDeleteTarget(null);
      }
    },
    [client, fetchSkills],
  );

  const openEditDialog = useCallback(
    async (skill: Skill) => {
      try {
        const data = await client.skills.get(skill.name);
        setEditorState({ open: true, mode: "edit", name: skill.name, content: data.content || "" });
      } catch (err) {
        setError(`Failed to load skill content: ${err}`);
      }
    },
    [client],
  );

  const availableSourceTypes = Array.from(
    new Set(skills.flatMap((s) => s.installed_in)),
  );

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-accent-teal-subtle">
            <Code2 className="w-5 h-5 text-accent-teal" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-primary">Skills</h2>
            <p className="text-sm text-secondary">Manage and sync skills across agent interfaces</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => guardAction(() => setEditorState({ open: true, mode: "create", name: "", content: "" }))}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-md transition"
          >
            <Plus className="w-3.5 h-3.5" />
            New Skill
          </button>
          <button
            onClick={() => fetchSkills(true)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-secondary hover:text-primary bg-control hover:bg-control-hover border border-card rounded-md transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Skill explanation */}
      <div className="mb-5 px-4 py-3.5 rounded-lg border border-teal-300 dark:border-teal-800/40 bg-teal-50 dark:bg-teal-950/20 overflow-hidden">
        <div className="flex items-center gap-3">
          <div className="shrink-0 p-2 rounded-lg bg-teal-100 dark:bg-teal-500/15 border border-teal-200 dark:border-teal-500/20">
            <Info className="w-4 h-4 text-teal-600 dark:text-teal-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-primary">What's a skill?</p>
            <p className="text-sm text-secondary mt-0.5">
              A skill is an instruction file that tells your coding agent how to handle specific tasks, like a personalized rulebook. Create them here, install community skills from the <span className="font-semibold text-primary">Explore</span> tab, or let VibeLens generate them from your coding sessions.
            </p>
          </div>
        </div>
      </div>

      <SourceFilterBar
        items={availableSourceTypes}
        activeKey={sourceFilter}
        onSelect={setSourceFilter}
        totalCount={skills.length}
        countByKey={(key) =>
          skills.filter((s) => s.installed_in.includes(key)).length
        }
      />

      <SearchBar value={searchQuery} onChange={handleSearchChange} />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {loading && skills.length === 0 && <LoadingState label="Loading skills..." />}

      {!loading && !error && skills.length === 0 && (
        <EmptyState
          icon={Package}
          title="No skills installed"
          subtitle="Skills are loaded from ~/.claude/skills/ and ~/.codex/skills/ on startup"
        >
          <button
            onClick={() => guardAction(() => setEditorState({ open: true, mode: "create", name: "", content: "" }))}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-md transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Create your first skill
          </button>
        </EmptyState>
      )}

      {!loading && skills.length > 0 && filteredSkills.length === 0 && <NoResultsState />}

      {filteredSkills.length > 0 && (
        <div className="space-y-2">
          <ResultCount filtered={filteredSkills.length} total={totalSkills} />
          {filteredSkills.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              onEdit={(s) => guardAction(() => openEditDialog(s))}
              onDelete={() => guardAction(() => setDeleteTarget(skill))}
              onViewDetail={setDetailSkill}
            />
          ))}
          <PaginationBar
            page={page}
            pageSize={pageSize}
            total={totalSkills}
            onPageChange={setPage}
            onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
          />
        </div>
      )}

      {editorState.open && (
        <EditorDialog
          mode={editorState.mode}
          initialName={editorState.name}
          initialContent={editorState.content}
          onSave={handleSave}
          onCancel={() => setEditorState(EDITOR_CLOSED)}
          saving={saving}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={`Delete "${deleteTarget.name}"?`}
          message="This removes the skill from the central store."
          confirmLabel="Delete"
          cancelLabel="Cancel"
          onConfirm={() => handleDelete(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        >
          {deleteTarget.installed_in.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-secondary mb-2">
                The skill will also be removed from these agents:
              </p>
              <ul className="space-y-1">
                {deleteTarget.installed_in.map((agent) => (
                  <li key={agent} className="flex items-center gap-2 text-xs text-muted px-2 py-1.5 rounded bg-control border border-card">
                    <span className="font-medium text-secondary">{agent}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </ConfirmDialog>
      )}

      {detailSkill && (
        <SkillDetailPopup
          skill={detailSkill}
          syncTargets={syncTargets}
          onClose={() => setDetailSkill(null)}
          onRefresh={fetchSkills}
        />
      )}

      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

/** Compact card for a locally installed skill in the list view. */
function SkillCard({
  skill,
  onEdit,
  onDelete,
  onViewDetail,
}: {
  skill: Skill;
  onEdit: (skill: Skill) => void;
  onDelete: () => void;
  onViewDetail: (skill: Skill) => void;
}) {
  const tags = skill.tags || [];
  const allowedTools = skill.allowed_tools || [];

  return (
    <div className="border border-card rounded-lg bg-panel hover:bg-control/80 transition">
      <div className="flex items-start">
        <button
          onClick={() => onViewDetail(skill)}
          className="flex-1 text-left px-4 py-3 flex items-start gap-3 min-w-0"
        >
          <div className="shrink-0 mt-0.5 p-1.5 rounded-md bg-accent-teal-subtle">
            <Package className="w-4 h-4 text-accent-teal" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-base font-bold text-primary">{skill.name}</span>
              {skill.installed_in.map((agent) => (
                <SourceBadge key={agent} sourceType={agent} sourcePath="" />
              ))}
            </div>
            <p className="text-sm text-secondary mt-1 line-clamp-2">
              {skill.description || "No description"}
            </p>
            <TagList tags={tags} />
            <ToolList tools={allowedTools} />
          </div>
        </button>
        <div className="flex items-center gap-1.5 px-3 py-3 shrink-0">
          <Tooltip text="Edit skill">
            <button
              onClick={() => onEdit(skill)}
              className="p-2 text-dimmed hover:text-accent-teal hover:bg-accent-teal-subtle rounded-md transition"
            >
              <Pencil className="w-4 h-4" />
            </button>
          </Tooltip>
          <Tooltip text="Delete skill">
            <button
              onClick={() => onDelete()}
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

/** Full-screen detail popup for a locally installed skill with sync controls. */
function SkillDetailPopup({
  skill: initialSkill,
  syncTargets,
  onClose,
  onRefresh,
}: {
  skill: Skill;
  syncTargets: ExtensionSyncTarget[];
  onClose: () => void;
  onRefresh: () => void;
}) {
  const client = useExtensionsClient();
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [skill, setSkill] = useState<Skill>(initialSkill);
  const [content, setContent] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [hoveredTarget, setHoveredTarget] = useState<string | null>(null);

  const tags = skill.tags || [];
  const allowedTools = skill.allowed_tools || [];

  useEffect(() => {
    client.skills.get(skill.name)
      .then((data) => setContent(data.content || ""))
      .catch(() => {})
      .finally(() => setLoadingContent(false));
  }, [client, skill.name]);

  const handleSync = useCallback(
    async (targetKey: string) => {
      setSyncing(targetKey);
      setSyncMessage(null);
      try {
        const data = await client.skills.syncToAgents(skill.name, [targetKey]);
        const results = data.results as Record<string, boolean>;
        const succeeded = results?.[targetKey] === true;
        if (succeeded) {
          setSyncMessage(`Synced to ${SOURCE_LABELS[targetKey] || targetKey}`);
          // Refresh skill data to update installed_in
          const refreshed = await client.skills.get(skill.name);
          const refreshedItem = refreshed.item as unknown as Skill;
          if (refreshedItem) setSkill(refreshedItem);
          onRefresh();
        } else {
          setSyncMessage(`Failed to sync to ${SOURCE_LABELS[targetKey] || targetKey}`);
        }
      } catch (err) {
        setSyncMessage(`Error: ${err}`);
      } finally {
        setSyncing(null);
      }
    },
    [client, skill.name, onRefresh],
  );

  const handleUnsync = useCallback(
    async (targetKey: string) => {
      setSyncing(targetKey);
      setSyncMessage(null);
      try {
        await client.skills.unsyncFromAgent(skill.name, targetKey);
        setSyncMessage(`Removed from ${SOURCE_LABELS[targetKey] || targetKey}`);
        const refreshed = await client.skills.get(skill.name);
        const refreshedItem = refreshed.item as unknown as Skill;
        if (refreshedItem) setSkill(refreshedItem);
        onRefresh();
      } catch (err) {
        setSyncMessage(`Error: ${err}`);
      } finally {
        setSyncing(null);
        setHoveredTarget(null);
      }
    },
    [client, skill.name, onRefresh],
  );

  return (
    <Modal onClose={onClose} maxWidth="max-w-2xl">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-accent-teal-subtle">
            <Package className="w-5 h-5 text-accent-teal" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold font-mono text-primary">{skill.name}</h2>
            </div>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              {skill.installed_in.map((agent) => (
                <SourceBadge key={agent} sourceType={agent} sourcePath="" />
              ))}
              {tags.map((tag) => <TagPill key={tag} tag={tag} />)}
            </div>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        <p className="text-sm text-secondary leading-relaxed">
          {skill.description || "No description"}
        </p>

        {allowedTools.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] text-muted">Tools</span>
              {allowedTools.map((tool) => <ToolBadge key={tool} tool={tool} />)}
            </div>
          </div>
        )}

        {syncTargets.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-2.5">
              <Share2 className="w-3.5 h-3.5 text-accent-teal" />
              <span className="text-xs font-semibold text-secondary">Sync to Agents</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {syncTargets.map((target) => {
                const isSynced = skill.installed_in.includes(target.agent);
                const hasDir = !!target.dir;
                const label = SOURCE_LABELS[target.agent] || target.agent;
                const isHovered = hoveredTarget === target.agent && isSynced;
                const tooltipText = isHovered
                  ? `Click to remove from ${label}`
                  : isSynced
                    ? `Synced to ${label}`
                    : hasDir
                      ? `Sync to ${target.dir}`
                      : `${label} not installed on this system`;
                return (
                  <Tooltip key={target.agent} text={tooltipText}>
                    <button
                      onClick={() => guardAction(() =>
                        isSynced ? handleUnsync(target.agent) : handleSync(target.agent)
                      )}
                      onMouseEnter={() => isSynced && setHoveredTarget(target.agent)}
                      onMouseLeave={() => setHoveredTarget(null)}
                      disabled={syncing === target.agent || (!isSynced && !hasDir)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full transition ${
                        isHovered
                          ? "bg-red-500/80 text-white"
                          : isSynced
                            ? "bg-emerald-600 text-white dark:bg-emerald-500"
                            : hasDir
                              ? "bg-control text-secondary border border-card hover:border-accent-teal/40 hover:text-accent-teal"
                              : "bg-subtle text-faint border border-card cursor-not-allowed opacity-50"
                      }`}
                    >
                      {isSynced ? <Check className="w-3 h-3" /> : <Share2 className="w-3 h-3 opacity-50" />}
                      {label}
                    </button>
                  </Tooltip>
                );
              })}
            </div>
            {syncMessage && (
              <p className="text-xs text-emerald-600/80 dark:text-emerald-400/70 mt-2">{syncMessage}</p>
            )}
          </div>
        )}

        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Code2 className="w-3.5 h-3.5 text-accent-teal" />
            <span className="text-xs font-semibold text-secondary">SKILL.md</span>
          </div>
          {loadingContent ? (
            <div className="flex items-center gap-2 py-6 justify-center">
              <span className="text-xs text-dimmed">Loading content...</span>
            </div>
          ) : content ? (
            <div className="rounded-lg border border-card bg-control/40 p-4 max-h-80 overflow-y-auto text-xs">
              <MarkdownRenderer content={content} />
            </div>
          ) : (
            <p className="text-xs text-dimmed italic py-4 text-center">No content available</p>
          )}
        </div>
      </ModalBody>

      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </Modal>
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
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
        <span>per page</span>
      </div>
      <div className="flex items-center gap-2">
        <span>{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}</span>
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

