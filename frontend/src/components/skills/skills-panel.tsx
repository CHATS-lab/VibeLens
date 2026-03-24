import {
  AlertCircle,
  Check,
  Code2,
  FileText,
  FolderOpen,
  Loader2,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { SkillInfo } from "../../types";
import { ConfirmDialog } from "../confirm-dialog";

const SUBDIR_LABELS: Record<string, string> = {
  scripts: "scripts/",
  references: "references/",
  agents: "agents/",
  assets: "assets/",
};

const SEARCH_DEBOUNCE_MS = 300;

/* ─── Skill Editor Dialog ─── */

function SkillEditorDialog({
  mode,
  initialName,
  initialContent,
  onSave,
  onCancel,
  saving,
}: {
  mode: "create" | "edit";
  initialName: string;
  initialContent: string;
  onSave: (name: string, content: string) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initialName);
  const [content, setContent] = useState(initialContent);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isCreate = mode === "create";
  const nameValid = /^[a-z0-9]+(-[a-z0-9]+)*$/.test(name);
  const contentValid = content.trim().length > 0;
  const canSave = nameValid && contentValid && !saving;

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl w-full max-w-3xl mx-4 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
          <h2 className="text-sm font-semibold text-zinc-100">
            {isCreate ? "Create New Skill" : `Edit: ${initialName}`}
          </h2>
          <button onClick={onCancel} className="text-zinc-500 hover:text-zinc-300 transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 flex-1 min-h-0 flex flex-col gap-3 overflow-hidden">
          {/* Name field */}
          {isCreate && (
            <div>
              <label className="block text-xs text-zinc-400 mb-1">
                Skill name <span className="text-zinc-600">(kebab-case)</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value.toLowerCase())}
                placeholder="my-new-skill"
                className={`w-full px-3 py-1.5 text-sm font-mono rounded bg-zinc-800 border text-zinc-100 outline-none focus:ring-1 transition ${
                  name && !nameValid
                    ? "border-red-500/50 focus:ring-red-500/30"
                    : "border-zinc-700 focus:ring-cyan-500/30 focus:border-cyan-600"
                }`}
              />
              {name && !nameValid && (
                <p className="text-[10px] text-red-400 mt-1">
                  Must be lowercase letters, numbers, and hyphens (e.g. my-skill-name)
                </p>
              )}
            </div>
          )}

          {/* Content editor */}
          <div className="flex-1 min-h-0 flex flex-col">
            <label className="block text-xs text-zinc-400 mb-1">SKILL.md content</label>
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={`---\nname: ${name || "my-skill"}\ndescription: What this skill does\n---\n\n# My Skill\n\nInstructions here...`}
              className="flex-1 min-h-[300px] w-full px-3 py-2 text-sm font-mono rounded bg-zinc-800 border border-zinc-700 text-zinc-100 outline-none focus:ring-1 focus:ring-cyan-500/30 focus:border-cyan-600 resize-none transition"
              spellCheck={false}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-zinc-800 shrink-0">
          <button
            onClick={onCancel}
            disabled={saving}
            className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => canSave && onSave(name, content)}
            disabled={!canSave}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-cyan-600 hover:bg-cyan-500 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Check className="w-3.5 h-3.5" />
            )}
            {isCreate ? "Create" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Skill Card ─── */

function SkillCard({
  skill,
  onEdit,
  onDelete,
}: {
  skill: SkillInfo;
  onEdit: (skill: SkillInfo) => void;
  onDelete: (name: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-zinc-700/50 rounded-lg bg-zinc-800/50 hover:bg-zinc-800/80 transition">
      <div className="flex items-start">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-1 text-left px-4 py-3 flex items-start gap-3 min-w-0"
        >
          <div className="shrink-0 mt-0.5 p-1.5 rounded-md bg-violet-600/20">
            <Package className="w-4 h-4 text-violet-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-semibold text-zinc-100">
                {skill.name}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-400 font-medium">
                {skill.agent_type}
              </span>
            </div>
            <p className="text-xs text-zinc-400 mt-1 line-clamp-2">
              {skill.description || "No description"}
            </p>
          </div>
          <div className="shrink-0 text-xs text-zinc-500 text-right">
            <span>{skill.line_count} lines</span>
          </div>
        </button>

        {/* Action buttons */}
        <div className="flex items-center gap-1 px-2 py-3 shrink-0">
          <button
            onClick={() => onEdit(skill)}
            className="p-1.5 text-zinc-500 hover:text-cyan-400 hover:bg-zinc-700 rounded transition"
            title="Edit skill"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onDelete(skill.name)}
            className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-zinc-700 rounded transition"
            title="Delete skill"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-3 border-t border-zinc-700/30 pt-3 space-y-2">
          {skill.allowed_tools.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1">
                <Wrench className="w-3 h-3" />
                <span>Allowed Tools</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {skill.allowed_tools.map((tool) => (
                  <span
                    key={tool}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-900/30 text-cyan-400 font-mono"
                  >
                    {tool}
                  </span>
                ))}
              </div>
            </div>
          )}

          {skill.subdirs.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-1">
                <FolderOpen className="w-3 h-3" />
                <span>Directories</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {skill.subdirs.map((dir) => (
                  <span
                    key={dir}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 font-mono"
                  >
                    {SUBDIR_LABELS[dir] || dir}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-1.5 text-xs text-zinc-500">
            <FileText className="w-3 h-3" />
            <span className="font-mono text-[10px] text-zinc-500 truncate">{skill.path}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Main Panel ─── */

export function SkillsPanel() {
  const { fetchWithToken } = useAppContext();
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filteredSkills, setFilteredSkills] = useState<SkillInfo[]>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Editor dialog state
  const [editorState, setEditorState] = useState<{
    open: boolean;
    mode: "create" | "edit";
    name: string;
    content: string;
  }>({ open: false, mode: "create", name: "", content: "" });
  const [saving, setSaving] = useState(false);

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithToken("/api/skills/local");
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

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  // Debounced search
  const handleSearchChange = useCallback(
    (query: string) => {
      setSearchQuery(query);
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);

      if (!query.trim()) {
        setFilteredSkills(skills);
        return;
      }

      searchTimerRef.current = setTimeout(async () => {
        try {
          const res = await fetchWithToken(
            `/api/skills/search?q=${encodeURIComponent(query)}`
          );
          if (res.ok) {
            const data: SkillInfo[] = await res.json();
            setFilteredSkills(data);
          }
        } catch {
          // Fall back to client-side filter on error
          const q = query.toLowerCase();
          setFilteredSkills(
            skills.filter(
              (s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
            )
          );
        }
      }, SEARCH_DEBOUNCE_MS);
    },
    [fetchWithToken, skills]
  );

  const openCreateDialog = useCallback(() => {
    setEditorState({ open: true, mode: "create", name: "", content: "" });
  }, []);

  const openEditDialog = useCallback(async (skill: SkillInfo) => {
    try {
      const res = await fetchWithToken(`/api/skills/local/${skill.name}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEditorState({
        open: true,
        mode: "edit",
        name: skill.name,
        content: data.content || "",
      });
    } catch (err) {
      setError(`Failed to load skill content: ${err}`);
    }
  }, [fetchWithToken]);

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

        setEditorState({ open: false, mode: "create", name: "", content: "" });
        await fetchSkills();
      } catch (err) {
        setError(String(err));
      } finally {
        setSaving(false);
      }
    },
    [editorState.mode, fetchWithToken, fetchSkills]
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
    [fetchWithToken, fetchSkills]
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-violet-600/20">
              <Code2 className="w-5 h-5 text-violet-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-zinc-100">Local Skills</h2>
              <p className="text-xs text-zinc-500">
                Manage installed Claude Code skills
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={openCreateDialog}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-violet-600 hover:bg-violet-500 rounded-md transition"
            >
              <Plus className="w-3.5 h-3.5" />
              New Skill
            </button>
            <button
              onClick={fetchSkills}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 rounded-md transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Search bar */}
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search skills by name or description..."
            className="w-full pl-9 pr-3 py-2 text-sm rounded-md bg-zinc-800 border border-zinc-700 text-zinc-100 placeholder:text-zinc-600 outline-none focus:ring-1 focus:ring-cyan-500/30 focus:border-cyan-600 transition"
          />
          {searchQuery && (
            <button
              onClick={() => handleSearchChange("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-red-900/20 border border-red-800/30 mb-4">
            <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
            <p className="text-sm text-red-300">{error}</p>
            <button
              onClick={() => setError(null)}
              className="ml-auto shrink-0 text-red-400 hover:text-red-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Loading */}
        {loading && skills.length === 0 && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
            <span className="ml-2 text-sm text-zinc-500">Loading skills...</span>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && skills.length === 0 && (
          <div className="text-center py-16">
            <Package className="w-10 h-10 text-zinc-600 mx-auto mb-3" />
            <p className="text-sm font-medium text-zinc-400 mb-1">No skills installed</p>
            <p className="text-xs text-zinc-600 mb-4">
              Skills live in ~/.claude/skills/ as SKILL.md files
            </p>
            <button
              onClick={openCreateDialog}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-violet-600 hover:bg-violet-500 rounded-md transition"
            >
              <Plus className="w-3.5 h-3.5" />
              Create your first skill
            </button>
          </div>
        )}

        {/* No search results */}
        {!loading && skills.length > 0 && filteredSkills.length === 0 && searchQuery && (
          <div className="text-center py-12">
            <Search className="w-8 h-8 text-zinc-600 mx-auto mb-2" />
            <p className="text-sm text-zinc-400">
              No skills matching "{searchQuery}"
            </p>
          </div>
        )}

        {/* Skill list */}
        {filteredSkills.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs text-zinc-500 mb-3">
              {searchQuery
                ? `${filteredSkills.length} result${filteredSkills.length !== 1 ? "s" : ""}`
                : `${skills.length} skill${skills.length !== 1 ? "s" : ""} installed`}
            </div>
            {filteredSkills.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onEdit={openEditDialog}
                onDelete={setDeleteTarget}
              />
            ))}
          </div>
        )}
      </div>

      {/* Editor dialog */}
      {editorState.open && (
        <SkillEditorDialog
          mode={editorState.mode}
          initialName={editorState.name}
          initialContent={editorState.content}
          onSave={handleSave}
          onCancel={() => setEditorState({ open: false, mode: "create", name: "", content: "" })}
          saving={saving}
        />
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <ConfirmDialog
          title="Delete Skill"
          message={`Are you sure you want to delete "${deleteTarget}"?\n\nThis will permanently remove the skill directory and all its files.`}
          confirmLabel="Delete"
          cancelLabel="Cancel"
          onConfirm={() => handleDelete(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
