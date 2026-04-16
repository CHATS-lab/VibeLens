import { Check, Download, Loader2, Monitor, RotateCcw, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { SkillSourceInfo } from "../../types";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../modal";
import { SOURCE_LABELS } from "./skill-constants";

interface SkillPreviewDialogProps {
  skillName: string;
  content: string;
  onContentChange?: (content: string) => void;
  onInstall: (content: string, targets: string[]) => void;
  onCancel: () => void;
  agentSources: SkillSourceInfo[];
  loading?: boolean;
  /** Use "install" for new skills (emerald), "update" for existing (amber). */
  variant?: "install" | "update";
}

/**
 * Shared preview dialog for skill content across all analysis modes.
 * Shows a scrollable, optionally editable textarea with install/update actions
 * and target agent selection.
 */
export function SkillPreviewDialog({
  skillName,
  content,
  onContentChange,
  onInstall,
  onCancel,
  agentSources,
  loading = false,
  variant = "install",
}: SkillPreviewDialogProps) {
  const [localContent, setLocalContent] = useState(content);
  const [selectedTargets, setSelectedTargets] = useState<Set<string>>(new Set());
  const [installing, setInstalling] = useState(false);

  // Sync local state when content prop updates (e.g. after async fetch)
  useEffect(() => {
    setLocalContent(content);
  }, [content]);
  const isEditable = !!onContentChange;
  const isUpdate = variant === "update";

  const accentClass = isUpdate ? "amber" : "emerald";
  const accentBg = isUpdate ? "bg-amber-600 hover:bg-amber-500" : "bg-emerald-600 hover:bg-emerald-500";
  const accentBorder = isUpdate ? "border-amber-600/40" : "border-teal-600/40";
  const actionLabel = isUpdate ? "Update" : "Install";
  const ActionIcon = isUpdate ? Upload : Download;

  const handleContentChange = useCallback(
    (value: string) => {
      setLocalContent(value);
      onContentChange?.(value);
    },
    [onContentChange],
  );

  const handleReset = useCallback(() => {
    setLocalContent(content);
    onContentChange?.(content);
  }, [content, onContentChange]);

  const toggleTarget = useCallback((key: string) => {
    setSelectedTargets((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    await onInstall(localContent, [...selectedTargets]);
    setInstalling(false);
  }, [onInstall, localContent, selectedTargets]);

  const title = isUpdate ? `Update: ${skillName}` : `Preview: ${skillName}`;
  const isModified = localContent !== content;

  return (
    <Modal onClose={onCancel} maxWidth="max-w-4xl">
      <ModalHeader title={title} onClose={onCancel} />
      <ModalBody>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 text-muted animate-spin" />
          </div>
        ) : (
          <>
            <div className="relative">
              <textarea
                value={localContent}
                onChange={isEditable ? (e) => handleContentChange(e.target.value) : undefined}
                readOnly={!isEditable}
                className={`w-full min-h-[300px] max-h-[50vh] bg-canvas text-secondary text-xs font-mono p-4 rounded-lg border focus:outline-none resize-y leading-relaxed ${
                  isEditable
                    ? `border-card focus:border-${accentClass}-600/50`
                    : "border-default/50 cursor-default"
                }`}
                spellCheck={false}
              />
              {isEditable && isModified && (
                <button
                  onClick={handleReset}
                  className="absolute top-2 right-2 flex items-center gap-1 text-[10px] text-dimmed hover:text-secondary px-2 py-1 rounded bg-control/80 border border-card transition"
                >
                  <RotateCcw className="w-2.5 h-2.5" /> Reset
                </button>
              )}
            </div>

            {/* Central store */}
            <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-accent-teal-subtle border border-accent-teal-border">
              <Check className="w-4 h-4 text-accent-teal shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-secondary">Central Store</p>
                <p className="text-xs text-dimmed">~/.vibelens/skills/</p>
              </div>
              <span className="text-[10px] text-accent-teal font-medium px-1.5 py-0.5 rounded bg-accent-teal-subtle">Always</span>
            </div>

            {/* Agent interface checkboxes */}
            {agentSources.length > 0 && (
              <div className="space-y-2">
                {agentSources.map((src) => {
                  const isSelected = selectedTargets.has(src.key);
                  return (
                    <button
                      key={src.key}
                      onClick={() => toggleTarget(src.key)}
                      className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border transition text-left ${
                        isSelected
                          ? `bg-control ${accentBorder}`
                          : "bg-subtle border-card hover:border-hover"
                      }`}
                    >
                      <div className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition ${
                        isSelected
                          ? `${accentBg.split(" ")[0]} border-${accentClass}-500`
                          : "border-hover"
                      }`}>
                        {isSelected && <Check className="w-3 h-3 text-white" />}
                      </div>
                      <Monitor className="w-4 h-4 text-muted shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-secondary">
                          {SOURCE_LABELS[src.key] || src.label}
                        </p>
                        <p className="text-xs text-dimmed truncate">{src.skills_dir}</p>
                      </div>
                      <span className="text-[10px] text-dimmed">
                        {src.skill_count} skill{src.skill_count !== 1 ? "s" : ""}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </>
        )}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          disabled={installing}
          className="px-3 py-1.5 text-xs text-muted hover:text-secondary border border-card hover:border-hover rounded transition disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={handleInstall}
          disabled={installing || loading}
          className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white ${accentBg} rounded transition disabled:opacity-50`}
        >
          {installing
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <ActionIcon className="w-3.5 h-3.5" />}
          {selectedTargets.size > 0
            ? `${actionLabel} & Sync to ${selectedTargets.size}`
            : `${actionLabel} to Central`}
        </button>
      </ModalFooter>
    </Modal>
  );
}
