import {
  Check,
  Code2,
  Loader2,
  Package,
  Pencil,
  Share2,
  FileText,
  Tag,
  Trash2,
  Wrench,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import type { SkillInfo, SkillSourceInfo } from "../../types";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { MarkdownRenderer } from "../markdown-renderer";
import { Modal, ModalHeader, ModalBody } from "../modal";
import { Tooltip } from "../tooltip";
import { SourceBadge, SubdirList, TagList, TagPill, ToolBadge, ToolList } from "./skill-badges";
import { SOURCE_LABELS } from "./skill-constants";

/** Compact card for a locally installed skill in the list view. */
export function SkillCard({
  skill,
  onEdit,
  onDelete,
  onViewDetail,
}: {
  skill: SkillInfo;
  onEdit: (skill: SkillInfo) => void;
  onDelete: (name: string) => void;
  onViewDetail: (skill: SkillInfo) => void;
}) {
  const tags = (skill.metadata?.tags as string[]) || [];
  const lineCount = (skill.metadata?.line_count as number) || 0;
  const allowedTools = (skill.metadata?.allowed_tools as string[]) || [];

  return (
    <div className="border border-zinc-700/50 rounded-lg bg-zinc-800/50 hover:bg-zinc-800/80 transition">
      <div className="flex items-start">
        <button
          onClick={() => onViewDetail(skill)}
          className="flex-1 text-left px-4 py-3 flex items-start gap-3 min-w-0"
        >
          <div className="shrink-0 mt-0.5 p-1.5 rounded-md bg-teal-600/20">
            <Package className="w-4 h-4 text-teal-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm font-semibold text-zinc-100">{skill.name}</span>
              {skill.sources
                .filter((s) => s.source_type !== "central")
                .map((src) => (
                  <SourceBadge key={src.source_type} sourceType={src.source_type} sourcePath={src.source_path} />
                ))}
              {lineCount > 0 && (
                <span className="text-xs text-zinc-400">{lineCount} lines</span>
              )}
            </div>
            <p className="text-sm text-zinc-200 mt-1 line-clamp-2">
              {skill.description || "No description"}
            </p>
            <TagList tags={tags} />
            <ToolList tools={allowedTools} />
          </div>
        </button>
        <div className="flex items-center gap-1 px-2 py-3 shrink-0">
          <button
            onClick={() => onEdit(skill)}
            className="p-1.5 text-zinc-500 hover:text-teal-400 hover:bg-zinc-700 rounded transition"
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
    </div>
  );
}

/** Full-screen detail popup for a locally installed skill, with sync controls. */
export function SkillDetailPopup({
  skill: initialSkill,
  agentSources,
  onClose,
  fetchWithToken,
  onRefresh,
}: {
  skill: SkillInfo;
  agentSources: SkillSourceInfo[];
  onClose: () => void;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onRefresh: () => void;
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [skill, setSkill] = useState<SkillInfo>(initialSkill);
  const [content, setContent] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const tags = useMemo(() => (skill.metadata?.tags as string[]) || [], [skill.metadata]);
  const allowedTools = useMemo(() => (skill.metadata?.allowed_tools as string[]) || [], [skill.metadata]);
  const subdirs = useMemo(() => (skill.metadata?.subdirs as string[]) || [], [skill.metadata]);
  const lineCount = (skill.metadata?.line_count as number) || 0;

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchWithToken(`/api/skills/local/${skill.name}`);
        if (res.ok) {
          const data = await res.json();
          setContent(data.content || "");
        }
      } catch {
        /* ignore */
      } finally {
        setLoadingContent(false);
      }
    })();
  }, [fetchWithToken, skill.name]);

  const handleSync = useCallback(
    async (targetKey: string) => {
      setSyncing(targetKey);
      setSyncMessage(null);
      try {
        const res = await fetchWithToken(`/api/skills/sync/${skill.name}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ targets: [targetKey] }),
        });
        if (res.ok) {
          const data = await res.json();
          const result = data.results?.[targetKey];
          if (result?.synced) {
            setSyncMessage(`Synced to ${SOURCE_LABELS[targetKey] || targetKey}`);
            if (data.skill) setSkill(data.skill as SkillInfo);
            onRefresh();
          } else {
            setSyncMessage(`Failed: ${result?.error || "Unknown error"}`);
          }
        }
      } catch (err) {
        setSyncMessage(`Error: ${err}`);
      } finally {
        setSyncing(null);
      }
    },
    [fetchWithToken, skill.name, onRefresh],
  );

  return (
    <Modal onClose={onClose} maxWidth="max-w-3xl">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-teal-600/20">
            <Package className="w-5 h-5 text-teal-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold font-mono text-white">{skill.name}</h2>
            {lineCount > 0 && (
              <span className="text-xs text-zinc-300">{lineCount} lines in SKILL.md</span>
            )}
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        {/* Skill Description */}
        <div>
          <SectionTitle icon={<FileText className="w-4 h-4" />} label="Skill Description" />
          <p className="text-sm text-zinc-200 leading-relaxed">
            {skill.description || "No description"}
          </p>
        </div>

        {/* Metadata grid: tags, tools, subdirs */}
        {(tags.length > 0 || allowedTools.length > 0 || subdirs.length > 0) && (
          <div className="rounded-lg border border-zinc-700/40 bg-zinc-800/30 divide-y divide-zinc-700/30">
            {/* Tags + Tools row */}
            {(tags.length > 0 || allowedTools.length > 0) && (
              <div className="px-4 py-3 flex flex-wrap gap-x-6 gap-y-2">
                {tags.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <SectionLabel icon={<Tag className="w-3 h-3" />} label="Tags" inline />
                    {tags.map((tag) => <TagPill key={tag} tag={tag} />)}
                  </div>
                )}
                {allowedTools.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <SectionLabel icon={<Wrench className="w-3 h-3" />} label="Tools" inline />
                    {allowedTools.map((tool) => <ToolBadge key={tool} tool={tool} />)}
                  </div>
                )}
              </div>
            )}

            {/* Subdirectories */}
            {subdirs.length > 0 && (
              <div className="px-4 py-3">
                <SectionLabel label="Directories" inline />
                <SubdirList dirs={subdirs} />
              </div>
            )}
          </div>
        )}

        {/* Sync to agent interfaces — show all agents from backend */}
        {agentSources.length > 0 && (
          <div className="rounded-lg border border-teal-700/30 bg-teal-950/10 px-4 py-3">
            <SectionTitle icon={<Share2 className="w-4 h-4" />} label="Sync to Agent Interfaces" />
            <div className="flex flex-wrap gap-2">
              {agentSources.map((src) => {
                const installedSource = skill.sources.find((s) => s.source_type === src.key);
                const isSynced = !!installedSource || skill.skill_targets.includes(src.key);
                const hasDir = !!src.skills_dir;
                const tooltipText = isSynced
                  ? installedSource?.source_path ?? `Synced to ${src.label}`
                  : hasDir
                    ? `Sync to ${src.skills_dir}`
                    : `${src.label} not installed on this system`;
                return (
                  <Tooltip key={src.key} text={tooltipText}>
                    <button
                      onClick={() => guardAction(() => handleSync(src.key))}
                      disabled={syncing === src.key || (!isSynced && !hasDir)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border transition ${
                        isSynced
                          ? "bg-emerald-900/20 text-emerald-400 border-emerald-700/30"
                          : hasDir
                            ? "bg-zinc-800/60 text-zinc-400 border-zinc-600/50 hover:text-teal-300 hover:border-teal-600/50 hover:bg-teal-950/20"
                            : "bg-zinc-800/30 text-zinc-600 border-zinc-700/30 cursor-not-allowed"
                      } disabled:opacity-50`}
                    >
                      {syncing === src.key ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : isSynced ? (
                        <Check className="w-3 h-3" />
                      ) : (
                        <Share2 className="w-3 h-3" />
                      )}
                      {src.label}
                    </button>
                  </Tooltip>
                );
              })}
            </div>
            {syncMessage && (
              <p className="text-xs text-emerald-400/70 mt-1.5">{syncMessage}</p>
            )}
          </div>
        )}

        {/* Skill Content */}
        <div>
          <SectionTitle icon={<Code2 className="w-4 h-4" />} label="Skill Content" />
          {loadingContent ? (
            <div className="flex items-center gap-2 py-4">
              <Loader2 className="w-4 h-4 text-zinc-500 animate-spin" />
              <span className="text-xs text-zinc-500">Loading...</span>
            </div>
          ) : content ? (
            <div className="bg-zinc-800/80 rounded-lg p-4 max-h-80 overflow-y-auto border border-zinc-700/30">
              <MarkdownRenderer content={_stripFrontmatter(content)} />
            </div>
          ) : (
            <p className="text-xs text-zinc-500 italic">No content</p>
          )}
        </div>
      </ModalBody>

      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </Modal>
  );
}

/** Prominent section title with icon for major sections in detail popups. */
function SectionTitle({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-2.5">
      <span className="text-teal-400">{icon}</span>
      <span className="text-sm font-semibold text-zinc-100">{label}</span>
    </div>
  );
}

/** Small label used as section header or inline label inside detail popups. */
function SectionLabel({ icon, label, inline }: { icon?: React.ReactNode; label: string; inline?: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 text-xs text-zinc-400 shrink-0 ${inline ? "" : "mb-2"}`}>
      {icon}
      <span>{label}</span>
    </div>
  );
}

/** Strip YAML frontmatter (--- ... ---) from SKILL.md content for rendering. */
function _stripFrontmatter(text: string): string {
  const match = text.match(/^---\n[\s\S]*?\n---\n?/);
  return match ? text.slice(match[0].length).trimStart() : text;
}
