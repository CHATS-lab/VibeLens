import {
  Check,
  Code2,
  FolderOpen,
  Loader2,
  Package,
  Pencil,
  Share2,
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
import { SourceBadge, SubdirBadge, TagList, TagPill, ToolBadge, ToolList } from "./skill-badges";
import { normalizeSourceType, SOURCE_LABELS } from "./skill-constants";

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
              {skill.sources
                .filter((s) => s.source_type !== "central")
                .map((src) => (
                  <SourceBadge key={src.source_type} sourceType={src.source_type} sourcePath={src.source_path} />
                ))}
              {lineCount > 0 && (
                <span className="text-xs text-muted">{lineCount} lines</span>
              )}
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
              onClick={() => onDelete(skill.name)}
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
            setSyncMessage(`Synced to ${SOURCE_LABELS[normalizeSourceType(targetKey)] || targetKey}`);
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
    <Modal onClose={onClose} maxWidth="max-w-2xl">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-accent-teal-subtle">
            <Package className="w-5 h-5 text-accent-teal" />
          </div>
          <div>
            <h2 className="text-lg font-bold font-mono text-primary">{skill.name}</h2>
            <div className="flex items-center gap-2 mt-0.5 flex-wrap">
              {lineCount > 0 && (
                <span className="text-[11px] text-muted">{lineCount} lines</span>
              )}
              {skill.sources
                .filter((s) => s.source_type !== "central")
                .map((src) => (
                  <SourceBadge key={src.source_type} sourceType={src.source_type} sourcePath={src.source_path} />
                ))}
              {tags.map((tag) => <TagPill key={tag} tag={tag} />)}
            </div>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        {/* Description */}
        <p className="text-sm text-secondary leading-relaxed">
          {skill.description || "No description"}
        </p>

        {/* Metadata chips */}
        {(allowedTools.length > 0 || subdirs.length > 0) && (
          <div className="space-y-3">
            {allowedTools.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1 text-[11px] text-muted shrink-0">
                  <Wrench className="w-3 h-3" /> Tools
                </span>
                {allowedTools.map((tool) => <ToolBadge key={tool} tool={tool} />)}
              </div>
            )}
            {subdirs.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1 text-[11px] text-muted shrink-0">
                  <FolderOpen className="w-3 h-3" /> Dirs
                </span>
                {subdirs.map((dir) => <SubdirBadge key={dir} dir={dir} />)}
              </div>
            )}
          </div>
        )}

        {/* Sync to agent interfaces */}
        {agentSources.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-2.5">
              <Share2 className="w-3.5 h-3.5 text-accent-teal" />
              <span className="text-xs font-semibold text-secondary">Sync to Agents</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {agentSources.map((src) => {
                const installedSource = skill.sources.find((s) => s.source_type === src.key);
                const isSynced = !!installedSource;
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
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full transition ${
                        isSynced
                          ? "bg-emerald-600 text-white dark:bg-emerald-500"
                          : hasDir
                            ? "bg-control text-secondary border border-card hover:border-accent-teal/40 hover:text-accent-teal"
                            : "bg-subtle text-faint border border-card cursor-not-allowed opacity-50"
                      }`}
                    >
                      {syncing === src.key ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : isSynced ? (
                        <Check className="w-3 h-3" />
                      ) : (
                        <Share2 className="w-3 h-3 opacity-50" />
                      )}
                      {src.label}
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

        {/* Skill content */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Code2 className="w-3.5 h-3.5 text-accent-teal" />
            <span className="text-xs font-semibold text-secondary">SKILL.md</span>
          </div>
          {loadingContent ? (
            <div className="flex items-center gap-2 py-6 justify-center">
              <Loader2 className="w-4 h-4 text-accent-teal/60 animate-spin" />
              <span className="text-xs text-dimmed">Loading content...</span>
            </div>
          ) : content ? (
            <div className="rounded-lg border border-card bg-control/40 p-4 max-h-80 overflow-y-auto text-xs">
              <MarkdownRenderer content={_stripFrontmatter(content)} />
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

/** Strip YAML frontmatter (--- ... ---) from SKILL.md content for rendering. */
function _stripFrontmatter(text: string): string {
  const match = text.match(/^---\n[\s\S]*?\n---\n?/);
  return match ? text.slice(match[0].length).trimStart() : text;
}
