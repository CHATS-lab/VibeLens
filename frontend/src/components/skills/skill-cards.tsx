import {
  Check,
  Code2,
  Copy,
  FileText,
  Loader2,
  Package,
  Pencil,
  Share2,
  Tag,
  Trash2,
  Wrench,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Tooltip } from "../tooltip";
import { Modal, ModalHeader, ModalBody } from "../modal";
import { MarkdownRenderer } from "../markdown-renderer";
import { SourceBadge, SubdirList, TagList, TagPill, ToolBadge, ToolList } from "./skill-badges";
import { SOURCE_LABELS } from "./skill-constants";
import type { SkillInfo, SkillSourceInfo } from "../../types";

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
                <span className="text-[10px] text-zinc-500">{lineCount} lines</span>
              )}
            </div>
            <p className="text-xs text-zinc-400 mt-1 line-clamp-2">
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
          <div className="p-1.5 rounded-md bg-teal-600/20">
            <Package className="w-4 h-4 text-teal-400" />
          </div>
          <div>
            <h2 className="text-base font-bold font-mono text-white">{skill.name}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              {skill.sources
                .filter((s) => s.source_type !== "central")
                .map((src) => (
                  <SourceBadge key={src.source_type} sourceType={src.source_type} sourcePath={src.source_path} />
                ))}
              {lineCount > 0 && <span className="text-[10px] text-zinc-500">{lineCount} lines</span>}
            </div>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        <p className="text-sm text-zinc-300 leading-relaxed">
          {skill.description || "No description"}
        </p>

        {/* Sources */}
        {skill.sources.length > 0 && (
          <div>
            <SectionLabel icon={<FileText className="w-3 h-3" />} label="Sources" />
            <div className="space-y-1.5">
              {skill.sources.map((src, i) => (
                <div key={i} className="flex items-center gap-2">
                  <SourceBadge sourceType={src.source_type} sourcePath={src.source_path} />
                  <span className="text-[10px] text-zinc-500 font-mono truncate">{src.source_path}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tags */}
        {tags.length > 0 && (
          <div>
            <SectionLabel icon={<Tag className="w-3 h-3" />} label="Tags" />
            <div className="flex flex-wrap gap-1.5">
              {tags.map((tag) => <TagPill key={tag} tag={tag} />)}
            </div>
          </div>
        )}

        {/* Allowed Tools */}
        {allowedTools.length > 0 && (
          <div>
            <SectionLabel icon={<Wrench className="w-3 h-3" />} label="Allowed Tools" />
            <div className="flex flex-wrap gap-1.5">
              {allowedTools.map((tool) => <ToolBadge key={tool} tool={tool} />)}
            </div>
          </div>
        )}

        {/* Subdirectories */}
        {subdirs.length > 0 && (
          <div>
            <SectionLabel label="Directories" />
            <SubdirList dirs={subdirs} />
          </div>
        )}

        {/* Sync to agent interfaces */}
        {agentSources.length > 0 && (
          <div>
            <SectionLabel icon={<Share2 className="w-3 h-3" />} label="Sync to Agent Interfaces" />
            <div className="flex flex-wrap gap-2">
              {agentSources.map((src) => {
                const isSynced = skill.skill_targets.includes(src.key) ||
                  skill.sources.some((s) => s.source_type === src.key);
                return (
                  <Tooltip key={src.key} text={isSynced ? `Already synced to ${src.label}` : `Copy skill to ${src.label} (${src.skills_dir})`}>
                    <button
                      onClick={() => handleSync(src.key)}
                      disabled={syncing === src.key}
                      className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium rounded-md border transition ${
                        isSynced
                          ? "bg-emerald-900/20 text-emerald-400 border-emerald-700/30"
                          : "text-zinc-400 border-zinc-700/50 hover:text-zinc-200 hover:border-zinc-600"
                      } disabled:opacity-50`}
                    >
                      {syncing === src.key ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : isSynced ? (
                        <Check className="w-3 h-3" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                      {src.label}
                    </button>
                  </Tooltip>
                );
              })}
            </div>
            {syncMessage && (
              <p className="text-[10px] text-emerald-400/70 mt-1.5">{syncMessage}</p>
            )}
          </div>
        )}

        {/* Content preview — rendered as markdown */}
        <div>
          <SectionLabel icon={<Code2 className="w-3 h-3" />} label="SKILL.md Content" />
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
    </Modal>
  );
}

/** Small label row used as section header inside detail popups. */
function SectionLabel({ icon, label }: { icon?: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-2">
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
