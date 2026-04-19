import { AlertTriangle, Loader2, Trash2 } from "lucide-react";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../../ui/modal";
import { SOURCE_LABELS } from "../constants";

interface UninstallExtensionDialogProps {
  /** Lowercase label for the entity type (e.g. "skill", "subagent"). */
  entityLabel: string;
  /** Display name of the item being uninstalled. */
  name: string;
  /** Agent keys the item is currently synced to. */
  installedIn: string[];
  /** True while the confirm action is running. */
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Destructive uninstall confirmation used by the card and the detail page.
 *
 * Lists every agent the extension is currently installed in and warns that
 * confirming will remove it from all of them plus the central store.
 */
export function UninstallExtensionDialog({
  entityLabel,
  name,
  installedIn,
  loading = false,
  onConfirm,
  onCancel,
}: UninstallExtensionDialogProps) {
  return (
    <Modal onClose={onCancel} maxWidth="max-w-md">
      <ModalHeader title={`Uninstall "${name}"?`} onClose={onCancel} />
      <ModalBody>
        <div className="flex items-start gap-3 px-4 py-3 rounded-lg border border-rose-200 dark:border-rose-800/40 bg-rose-50 dark:bg-rose-950/20">
          <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-300 shrink-0 mt-0.5" />
          <p className="text-sm text-secondary">
            This removes the {entityLabel} from the central store and from every
            agent it is currently synced to.
          </p>
        </div>

        {installedIn.length > 0 ? (
          <div>
            <p className="text-xs font-medium text-secondary mb-2">
              Will be removed from {installedIn.length}{" "}
              {installedIn.length === 1 ? "agent" : "agents"}:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {installedIn.map((agent) => (
                <span
                  key={agent}
                  className="text-xs px-2.5 py-1 rounded-full bg-control text-secondary font-medium"
                >
                  {SOURCE_LABELS[agent] || agent}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted italic">
            Not currently synced to any agent.
          </p>
        )}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          disabled={loading}
          className="px-3 py-1.5 text-xs text-muted hover:text-secondary border border-card hover:border-hover rounded transition disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-rose-600 hover:bg-rose-500 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Trash2 className="w-3.5 h-3.5" />
          )}
          Uninstall
        </button>
      </ModalFooter>
    </Modal>
  );
}
