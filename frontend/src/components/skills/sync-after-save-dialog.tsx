import { Check, Loader2, Monitor, Share2, X } from "lucide-react";
import { useCallback, useState } from "react";
import type { SkillSourceInfo } from "../../types";
import { Modal, ModalBody, ModalFooter } from "../modal";
import { SOURCE_LABELS } from "./skill-constants";

interface SyncAfterSaveDialogProps {
  skillName: string;
  agentSources: SkillSourceInfo[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onClose: () => void;
}

/**
 * Dialog shown after saving a skill edit, asking whether to sync
 * the updated skill to other agent interfaces.
 */
export function SyncAfterSaveDialog({
  skillName,
  agentSources,
  fetchWithToken,
  onClose,
}: SyncAfterSaveDialogProps) {
  const [selectedTargets, setSelectedTargets] = useState<Set<string>>(new Set());
  const [syncing, setSyncing] = useState(false);
  const [syncDone, setSyncDone] = useState(false);

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

  const handleSync = useCallback(async () => {
    if (selectedTargets.size === 0) {
      onClose();
      return;
    }
    setSyncing(true);
    try {
      await fetchWithToken(`/api/skills/sync/${skillName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targets: [...selectedTargets] }),
      });
      setSyncDone(true);
      setTimeout(onClose, 800);
    } catch {
      onClose();
    }
  }, [fetchWithToken, skillName, selectedTargets, onClose]);

  return (
    <Modal onClose={onClose} maxWidth="max-w-md">
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
        <div className="flex items-center gap-2.5">
          <Share2 className="w-4 h-4 text-teal-400" />
          <h2 className="text-sm font-semibold text-zinc-100">
            Sync changes to agent interfaces?
          </h2>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition">
          <X className="w-4 h-4" />
        </button>
      </div>
      <ModalBody>
        <p className="text-sm text-zinc-400 leading-relaxed">
          You updated <span className="font-mono text-zinc-200">{skillName}</span>.
          Would you like to sync the changes to your agent interfaces?
        </p>

        {agentSources.length > 0 && (
          <div className="space-y-2">
            {agentSources.map((src) => {
              const isSelected = selectedTargets.has(src.key);
              return (
                <button
                  key={src.key}
                  onClick={() => toggleTarget(src.key)}
                  disabled={syncing || syncDone}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border transition text-left ${
                    isSelected
                      ? "bg-zinc-800 border-teal-600/40"
                      : "bg-zinc-800/50 border-zinc-700/50 hover:border-zinc-600"
                  } disabled:opacity-60`}
                >
                  <div className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition ${
                    isSelected
                      ? "bg-teal-600 border-teal-500"
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
                </button>
              );
            })}
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onClose}
          disabled={syncing}
          className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition disabled:opacity-50"
        >
          Skip
        </button>
        <button
          onClick={handleSync}
          disabled={syncing || syncDone}
          className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-500 rounded transition disabled:opacity-50"
        >
          {syncDone
            ? (<><Check className="w-3.5 h-3.5" /> Synced</>)
            : syncing
              ? (<Loader2 className="w-3.5 h-3.5 animate-spin" />)
              : (<><Share2 className="w-3.5 h-3.5" /> Sync</>)}
        </button>
      </ModalFooter>
    </Modal>
  );
}
