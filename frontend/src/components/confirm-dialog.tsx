import { X } from "lucide-react";

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  loading = false,
}: ConfirmDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-overlay backdrop-blur-sm"
        onClick={onCancel}
      />

      {/* Dialog */}
      <div className="relative bg-panel border border-card rounded-lg shadow-2xl w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-default">
          <h2 className="text-sm font-semibold text-primary">{title}</h2>
          <button
            onClick={onCancel}
            className="text-dimmed hover:text-secondary transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          <p className="text-sm text-secondary whitespace-pre-line">{message}</p>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-default">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-3 py-1.5 text-xs text-muted hover:text-secondary border border-card hover:border-hover rounded transition disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-3 py-1.5 text-xs text-white bg-cyan-600 hover:bg-cyan-500 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Sending..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
