import { Code2, Package, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { SkillInfo, SkillSourceInfo } from "../../types";
import { SEARCH_DEBOUNCE_MS } from "../../styles";
import { ConfirmDialog } from "../confirm-dialog";
import { SkillCard, SkillDetailPopup } from "./skill-cards";
import { SkillEditorDialog } from "./skill-editor-dialog";
import {
  EmptyState,
  ErrorBanner,
  LoadingState,
  NoResultsState,
  SkillCount,
  SkillSearchBar,
  SourceFilterBar,
} from "./skill-shared";

interface EditorState {
  open: boolean;
  mode: "create" | "edit";
  name: string;
  content: string;
}

const EDITOR_CLOSED: EditorState = { open: false, mode: "create", name: "", content: "" };

export function LocalSkillsTab() {
  const { fetchWithToken } = useAppContext();
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

  const fetchSkills = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const url = forceRefresh ? "/api/skills/local?refresh=true" : "/api/skills/local";
      const res = await fetchWithToken(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const data: SkillInfo[] = await res.json();
      setSkills(data);
      setFilteredSkills(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [fetchWithToken]);

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
        setEditorState(EDITOR_CLOSED);
        await fetchSkills();
      } catch (err) {
        setError(String(err));
      } finally {
        setSaving(false);
      }
    },
    [editorState.mode, fetchWithToken, fetchSkills],
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
    <div className="max-w-3xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-violet-600/20">
            <Code2 className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-zinc-100">Skills</h2>
            <p className="text-xs text-zinc-500">Manage and sync skills across agent interfaces</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setEditorState({ open: true, mode: "create", name: "", content: "" })}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-violet-600 hover:bg-violet-500 rounded-md transition"
          >
            <Plus className="w-3.5 h-3.5" />
            New Skill
          </button>
          <button
            onClick={() => { fetchSkills(true); fetchSources(); }}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 rounded-md transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
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
            onClick={() => setEditorState({ open: true, mode: "create", name: "", content: "" })}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-violet-600 hover:bg-violet-500 rounded-md transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Create your first skill
          </button>
        </EmptyState>
      )}

      {!loading && skills.length > 0 && filteredSkills.length === 0 && <NoResultsState />}

      {filteredSkills.length > 0 && (
        <div className="space-y-2">
          <SkillCount filtered={filteredSkills.length} total={skills.length} />
          {filteredSkills.map((skill) => (
            <SkillCard
              key={skill.name}
              skill={skill}
              onEdit={openEditDialog}
              onDelete={setDeleteTarget}
              onViewDetail={setDetailSkill}
            />
          ))}
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
    </div>
  );
}
