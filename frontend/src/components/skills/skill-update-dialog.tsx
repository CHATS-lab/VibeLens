import { Check, Loader2, Monitor, Upload } from "lucide-react";
import { useCallback, useState } from "react";
import type { SkillSourceInfo } from "../../types";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../modal";
import { SOURCE_LABELS } from "./skill-constants";

interface SkillUpdateDialogProps {
  skillName: string;
  initialContent: string;
  agentSources: SkillSourceInfo[];
  onUpdate: (content: string, targets: string[]) => void;
  onCancel: () => void;
  updating: boolean;
}

/**
 * Combined editor + target selection modal for applying evolution edits.
 * Users can review/tweak the merged SKILL.md content and choose which
 * agent interfaces to sync the updated skill to.
 */
export function SkillUpdateDialog({
  skillName,
  initialContent,
  agentSources,
  onUpdate,
  onCancel,
  updating,
}: SkillUpdateDialogProps) {
  const [content, setContent] = useState(initialContent);
  const [selectedTargets, setSelectedTargets] = useState<Set<string>>(new Set());

  const toggleTarget = useCallback((key: string) => {
    setSelectedTargets((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const handleUpdate = useCallback(() => {
    onUpdate(content, [...selectedTargets]);
  }, [onUpdate, content, selectedTargets]);

  return (
    <Modal onClose={onCancel} maxWidth="max-w-4xl">
      <ModalHeader title={`Update: ${skillName}`} onClose={onCancel} />
      <ModalBody>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="w-full min-h-[300px] bg-zinc-950 text-zinc-200 text-xs font-mono p-4 rounded-lg border border-zinc-700/50 focus:border-amber-600/50 focus:outline-none resize-y leading-relaxed"
          spellCheck={false}
        />

        {/* Central store — always selected */}
        <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-teal-900/15 border border-teal-700/30">
          <Check className="w-4 h-4 text-teal-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-zinc-200">Central Store</p>
            <p className="text-xs text-zinc-500">~/.vibelens/skills/</p>
          </div>
          <span className="text-[10px] text-teal-400 font-medium px-1.5 py-0.5 rounded bg-teal-900/30">Always</span>
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
                      ? "bg-zinc-800 border-amber-600/40"
                      : "bg-zinc-800/50 border-zinc-700/50 hover:border-zinc-600"
                  }`}
                >
                  <div className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition ${
                    isSelected
                      ? "bg-amber-600 border-amber-500"
                      : "border-zinc-600"
                  }`}>
                    {isSelected && <Check className="w-3 h-3 text-white" />}
                  </div>
                  <Monitor className="w-4 h-4 text-zinc-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-200">
                      {SOURCE_LABELS[src.key] || src.label}
                    </p>
                    <p className="text-xs text-zinc-500 truncate">{src.skills_dir}</p>
                  </div>
                  <span className="text-[10px] text-zinc-500">
                    {src.skill_count} skill{src.skill_count !== 1 ? "s" : ""}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          disabled={updating}
          className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={handleUpdate}
          disabled={updating}
          className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 rounded transition disabled:opacity-50"
        >
          {updating
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <Upload className="w-3.5 h-3.5" />}
          {selectedTargets.size > 0
            ? `Update & Sync to ${selectedTargets.size}`
            : "Update"}
        </button>
      </ModalFooter>
    </Modal>
  );
}
