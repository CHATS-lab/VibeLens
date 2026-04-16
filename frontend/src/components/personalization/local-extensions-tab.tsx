import { ChevronLeft, ChevronRight, Code2, Info, Package, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../../app";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import type { SkillInfo, SkillSourceInfo } from "../../types";
import { SEARCH_DEBOUNCE_MS } from "../../constants";
import { ConfirmDialog } from "../confirm-dialog";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { SkillCard, SkillDetailPopup } from "./skill-cards";
import { SkillEditorDialog } from "./skill-editor-dialog";
import { SyncAfterSaveDialog } from "./sync-after-save-dialog";
import { EmptyState } from "../empty-state";
import { ErrorBanner } from "../error-banner";
import { LoadingState } from "../loading-state";
import {
  NoResultsState,
  SkillCount,
  SkillSearchBar,
  SourceFilterBar,
} from "./skill-shared";

const DEFAULT_PAGE_SIZE = 50;
const PAGE_SIZE_OPTIONS = [25, 50, 100];

interface EditorState {
  open: boolean;
  mode: "create" | "edit";
  name: string;
  content: string;
}

const EDITOR_CLOSED: EditorState = { open: false, mode: "create", name: "", content: "" };

export function LocalSkillsTab() {
  const { fetchWithToken } = useAppContext();
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredSkills, setFilteredSkills] = useState<SkillInfo[]>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [editorState, setEditorState] = useState<EditorState>(EDITOR_CLOSED);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [detailSkill, setDetailSkill] = useState<SkillInfo | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [agentSources, setAgentSources] = useState<SkillSourceInfo[]>([]);
  const [syncPromptSkill, setSyncPromptSkill] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [totalSkills, setTotalSkills] = useState(0);

  const fetchSkills = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (forceRefresh) params.set("refresh", "true");
      const res = await fetchWithToken(`/api/skills/local?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data = await res.json();
      const items: SkillInfo[] = data.items ?? data;
      setSkills(items);
      setFilteredSkills(items);
      setTotalSkills(data.total ?? items.length);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [fetchWithToken, page, pageSize]);

  const fetchSources = useCallback(async () => {
    try {
      const res = await fetchWithToken("/api/skills/sources");
      if (res.ok) setAgentSources(await res.json());
    } catch {
      /* ignore */
    }
  }, [fetchWithToken]);

  useEffect(() => {
    fetchSkills();
    fetchSources();
  }, [fetchSkills, fetchSources]);

  // Apply source filter + search query
  useEffect(() => {
    let result = skills;
    if (sourceFilter) {
      result = result.filter((s) =>
        s.sources.some((src) => src.source_type === sourceFilter),
      );
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
          const res = await fetchWithToken(`/api/skills/search?q=${encodeURIComponent(query)}`);
          if (res.ok) {
            const data: SkillInfo[] = await res.json();
            setSkills(data);
          }
        } catch {
          /* fallback to local filter */
        }
      }, SEARCH_DEBOUNCE_MS);
    },
    [fetchWithToken, fetchSkills],
  );

  const handleSave = useCallback(
    async (name: string, content: string) => {
      setSaving(true);
      setError(null);
      try {
        const isCreate = editorState.mode === "create";
        const url = isCreate ? "/api/skills/install" : `/api/skills/local/${name}`;
        const method = isCreate ? "POST" : "PUT";
        const res = await fetchWithToken(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, content }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        const savedName = name;
        const wasEdit = !isCreate;
        setEditorState(EDITOR_CLOSED);
        await fetchSkills();
        // After editing, prompt to sync to agent interfaces
        if (wasEdit && agentSources.length > 0) {
          setSyncPromptSkill(savedName);
        }
      } catch (err) {
        setError(String(err));
      } finally {
        setSaving(false);
      }
    },
    [editorState.mode, fetchWithToken, fetchSkills, agentSources.length],
  );

  const handleDelete = useCallback(
    async (name: string) => {
      setError(null);
      try {
        const res = await fetchWithToken(`/api/skills/local/${name}`, { method: "DELETE" });
        if (!res.ok) {
          const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        setDeleteTarget(null);
        await fetchSkills();
      } catch (err) {
        setError(String(err));
        setDeleteTarget(null);
      }
    },
    [fetchWithToken, fetchSkills],
  );

  const openEditDialog = useCallback(
    async (skill: SkillInfo) => {
      try {
        const res = await fetchWithToken(`/api/skills/local/${skill.name}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setEditorState({ open: true, mode: "edit", name: skill.name, content: data.content || "" });
      } catch (err) {
        setError(`Failed to load skill content: ${err}`);
      }
    },
    [fetchWithToken],
  );

  const availableSourceTypes = Array.from(
    new Set(skills.flatMap((s) => s.sources.map((src) => src.source_type))),
  ).filter((t) => t !== "central");

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
            onClick={() => { fetchSkills(true); fetchSources(); }}
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
          skills.filter((s) => s.sources.some((src) => src.source_type === key)).length
        }
      />

      <SkillSearchBar value={searchQuery} onChange={handleSearchChange} />

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
          <SkillCount filtered={filteredSkills.length} total={totalSkills} />
          {filteredSkills.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              onEdit={(s) => guardAction(() => openEditDialog(s))}
              onDelete={(name) => guardAction(() => setDeleteTarget(name))}
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
        <SkillEditorDialog
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
          title="Delete Skill"
          message={`Delete "${deleteTarget}"? This removes the skill directory and all its files.`}
          confirmLabel="Delete"
          cancelLabel="Cancel"
          onConfirm={() => handleDelete(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {detailSkill && (
        <SkillDetailPopup
          skill={detailSkill}
          agentSources={agentSources}
          onClose={() => setDetailSkill(null)}
          fetchWithToken={fetchWithToken}
          onRefresh={fetchSkills}
        />
      )}

      {syncPromptSkill && (
        <SyncAfterSaveDialog
          skillName={syncPromptSkill}
          agentSources={agentSources}
          fetchWithToken={fetchWithToken}
          onClose={() => setSyncPromptSkill(null)}
        />
      )}

      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
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
