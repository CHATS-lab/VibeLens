import { Modal, ModalHeader, ModalBody, ModalFooter } from "./modal";

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  children?: React.ReactNode;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  loading = false,
  children,
}: ConfirmDialogProps) {
  return (
    <Modal onClose={onCancel} maxWidth="max-w-md">
      <ModalHeader title={title} onClose={onCancel} />
      <ModalBody>
        <p className="text-sm text-secondary whitespace-pre-line">{message}</p>
        {children}
      </ModalBody>
      <ModalFooter>
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
      </ModalFooter>
    </Modal>
  );
}
