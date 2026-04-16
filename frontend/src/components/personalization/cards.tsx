import {
  Check,
  Code2,
  Download,
  ExternalLink,
  Loader2,
  Package,
  Pencil,
  Share2,
  Star,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import type { Skill, SkillSyncTarget } from "../../types";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { MarkdownRenderer } from "../markdown-renderer";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "../modal";
import { Tooltip } from "../tooltip";
import { SourceBadge, TagList, TagPill, ToolBadge, ToolList } from "./badges";
import { SOURCE_LABELS } from "./constants";

/** Compact card for a locally installed skill in the list view. */
export function ExtensionCard({
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

/** Full-screen detail popup for a skill, with sync controls (sync mode) or install action (install mode). */
export function ExtensionDetailPopup({
  skill: initialSkill,
  syncTargets,
  onClose,
  fetchWithToken,
  onRefresh,
  mode = "sync",
  previewContent,
  loadingContent: externalLoadingContent,
  stars,
  sourceUrl,
  onInstall,
}: {
  skill: Skill;
  syncTargets: SkillSyncTarget[];
  onClose: () => void;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onRefresh: () => void;
  /** "sync" (default): skill is installed, show sync controls. "install": skill is a preview, show install action. */
  mode?: "sync" | "install";
  /** Preloaded content for install mode (skip the /api/skills/{name} fetch). */
  previewContent?: string;
  /** External loading state for install mode (while parent fetches catalog content). */
  loadingContent?: boolean;
  /** Star count for install mode (from catalog item). */
  stars?: number;
  /** Source URL for install mode (from catalog item). */
  sourceUrl?: string;
  /** Install handler for install mode. Receives content + selected agent targets. */
  onInstall?: (content: string, targets: string[]) => Promise<void>;
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [skill, setSkill] = useState<Skill>(initialSkill);
  const [content, setContent] = useState<string | null>(
    mode === "install" ? (previewContent ?? null) : null,
  );
  const [loadingContent, setLoadingContent] = useState(mode === "sync");
  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [hoveredTarget, setHoveredTarget] = useState<string | null>(null);
  const [selectedInstallTargets, setSelectedInstallTargets] = useState<Set<string>>(new Set());
  const [installing, setInstalling] = useState(false);

  const tags = useMemo(() => skill.tags || [], [skill.tags]);
  const allowedTools = useMemo(() => skill.allowed_tools || [], [skill.allowed_tools]);
  const isInstallMode = mode === "install";
  const effectiveLoadingContent = isInstallMode ? !!externalLoadingContent : loadingContent;
  const effectiveContent = isInstallMode ? (previewContent ?? "") : content;

  useEffect(() => {
    if (isInstallMode) return;
    (async () => {
      try {
        const res = await fetchWithToken(`/api/skills/${skill.name}`);
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
  }, [fetchWithToken, skill.name, isInstallMode]);

  const handleSync = useCallback(
    async (targetKey: string) => {
      setSyncing(targetKey);
      setSyncMessage(null);
      try {
        const res = await fetchWithToken(`/api/skills/${skill.name}/agents`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agents: [targetKey] }),
        });
        if (res.ok) {
          const data = await res.json();
          const succeeded = data.results?.[targetKey] === true;
          if (succeeded) {
            setSyncMessage(`Synced to ${SOURCE_LABELS[targetKey] || targetKey}`);
            if (data.skill) setSkill(data.skill as Skill);
            onRefresh();
          } else {
            setSyncMessage(`Failed to sync to ${SOURCE_LABELS[targetKey] || targetKey}`);
          }
        } else {
          const body = await res.json().catch(() => ({ detail: "Unknown error" }));
          setSyncMessage(`Failed: ${body.detail}`);
        }
      } catch (err) {
        setSyncMessage(`Error: ${err}`);
      } finally {
        setSyncing(null);
      }
    },
    [fetchWithToken, skill.name, onRefresh],
  );

  const handleUnsync = useCallback(
    async (targetKey: string) => {
      setSyncing(targetKey);
      setSyncMessage(null);
      try {
        const res = await fetchWithToken(`/api/skills/${skill.name}/agents/${targetKey}`, {
          method: "DELETE",
        });
        if (res.ok) {
          const data = await res.json();
          setSyncMessage(`Removed from ${SOURCE_LABELS[targetKey] || targetKey}`);
          if (data.skill) setSkill(data.skill as Skill);
          onRefresh();
        } else {
          const body = await res.json().catch(() => ({ detail: "Unknown error" }));
          setSyncMessage(`Failed: ${body.detail}`);
        }
      } catch (err) {
        setSyncMessage(`Error: ${err}`);
      } finally {
        setSyncing(null);
        setHoveredTarget(null);
      }
    },
    [fetchWithToken, skill.name, onRefresh],
  );

  const toggleInstallTarget = useCallback((key: string) => {
    setSelectedInstallTargets((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const handleInstallClick = useCallback(async () => {
    if (!onInstall || !effectiveContent) return;
    setInstalling(true);
    try {
      await onInstall(effectiveContent, [...selectedInstallTargets]);
      onClose();
    } catch (err) {
      setSyncMessage(`Failed: ${err}`);
    } finally {
      setInstalling(false);
    }
  }, [onInstall, effectiveContent, selectedInstallTargets, onClose]);

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
              {isInstallMode && typeof stars === "number" && stars > 0 && (
                <span className="inline-flex items-center gap-0.5 text-[11px] text-amber-500 dark:text-amber-400">
                  <Star className="w-3 h-3 fill-amber-400 text-amber-400" /> {stars.toLocaleString()}
                </span>
              )}
              {isInstallMode && sourceUrl && (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-dimmed hover:text-secondary transition"
                >
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
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
        {/* Description */}
        <p className="text-sm text-secondary leading-relaxed">
          {skill.description || "No description"}
        </p>

        {/* Metadata chips */}
        {allowedTools.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1 text-[11px] text-muted shrink-0">
                <Wrench className="w-3 h-3" /> Tools
              </span>
              {allowedTools.map((tool) => <ToolBadge key={tool} tool={tool} />)}
            </div>
          </div>
        )}

        {/* Sync to agent interfaces (sync mode only) */}
        {!isInstallMode && syncTargets.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-2.5">
              <Share2 className="w-3.5 h-3.5 text-accent-teal" />
              <span className="text-xs font-semibold text-secondary">Sync to Agents</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {syncTargets.map((target) => {
                const isSynced = skill.installed_in.includes(target.agent);
                const hasDir = !!target.skills_dir;
                const label = SOURCE_LABELS[target.agent] || target.agent;
                const isHovered = hoveredTarget === target.agent && isSynced;
                const tooltipText = isHovered
                  ? `Click to remove from ${label}`
                  : isSynced
                    ? `Synced to ${label}`
                    : hasDir
                      ? `Sync to ${target.skills_dir}`
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
                      {syncing === target.agent ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : isHovered ? (
                        <X className="w-3 h-3" />
                      ) : isSynced ? (
                        <Check className="w-3 h-3" />
                      ) : (
                        <Share2 className="w-3 h-3 opacity-50" />
                      )}
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

        {/* Install target selector (install mode only) */}
        {isInstallMode && syncTargets.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-2.5">
              <Share2 className="w-3.5 h-3.5 text-accent-teal" />
              <span className="text-xs font-semibold text-secondary">Sync to Agents</span>
              <span className="text-[10px] text-dimmed">(select at least one)</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {syncTargets.map((target) => {
                const isSelected = selectedInstallTargets.has(target.agent);
                const label = SOURCE_LABELS[target.agent] || target.agent;
                return (
                  <button
                    key={target.agent}
                    onClick={() => toggleInstallTarget(target.agent)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full border transition ${
                      isSelected
                        ? "bg-emerald-600 text-white border-emerald-600 dark:bg-emerald-500 dark:border-emerald-500"
                        : "bg-control text-secondary border-card hover:border-accent-teal/40 hover:text-accent-teal"
                    }`}
                  >
                    {isSelected ? <Check className="w-3 h-3" /> : <Share2 className="w-3 h-3 opacity-50" />}
                    {label}
                  </button>
                );
              })}
            </div>
            {syncMessage && (
              <p className="text-xs text-rose-600 dark:text-rose-400 mt-2">{syncMessage}</p>
            )}
          </div>
        )}

        {/* Skill content */}
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Code2 className="w-3.5 h-3.5 text-accent-teal" />
            <span className="text-xs font-semibold text-secondary">SKILL.md</span>
          </div>
          {effectiveLoadingContent ? (
            <div className="flex items-center gap-2 py-6 justify-center">
              <Loader2 className="w-4 h-4 text-accent-teal/60 animate-spin" />
              <span className="text-xs text-dimmed">Loading content...</span>
            </div>
          ) : effectiveContent ? (
            <div className="rounded-lg border border-card bg-control/40 p-4 max-h-80 overflow-y-auto text-xs">
              <MarkdownRenderer content={_stripFrontmatter(effectiveContent)} />
            </div>
          ) : (
            <p className="text-xs text-dimmed italic py-4 text-center">No content available</p>
          )}
        </div>
      </ModalBody>

      {isInstallMode && (
        <ModalFooter>
          <button
            onClick={onClose}
            disabled={installing}
            className="px-3 py-1.5 text-xs text-muted hover:text-secondary border border-card hover:border-hover rounded transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => guardAction(handleInstallClick)}
            disabled={
              installing
              || effectiveLoadingContent
              || !effectiveContent
              || selectedInstallTargets.size === 0
            }
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {installing
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Download className="w-3.5 h-3.5" />}
            {selectedInstallTargets.size > 0
              ? `Install & Sync to ${selectedInstallTargets.size} interface${selectedInstallTargets.size !== 1 ? "s" : ""}`
              : "Select an interface"}
          </button>
        </ModalFooter>
      )}

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
