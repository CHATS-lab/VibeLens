import { X } from "lucide-react";
import { createPortal } from "react-dom";

interface ModalProps {
  children: React.ReactNode;
  onClose: () => void;
  /** Max width class, e.g. "max-w-2xl" or "max-w-3xl". Defaults to "max-w-2xl". */
  maxWidth?: string;
}

/**
 * Full-screen overlay modal with consistent styling across the app.
 * Renders a backdrop, centered card, and optional close-on-backdrop.
 *
 * Portaled to document.body so modal DOM escapes ancestor stacking contexts
 * and overflow clipping. Stops click propagation at the overlay root so
 * React synthetic events don't bubble to a click-handling ancestor in the
 * React tree (e.g. a card that navigates to a detail view). React synthetic
 * events propagate along the JSX tree, not the DOM tree, so the portal alone
 * is not enough.
 */
export function Modal({ children, onClose, maxWidth = "max-w-2xl" }: ModalProps) {
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="absolute inset-0 bg-overlay backdrop-blur-sm" onClick={onClose} />
      <div
        className={`relative bg-panel border border-card rounded-lg shadow-2xl w-full ${maxWidth} mx-4 flex flex-col max-h-[85vh]`}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

/** Standard modal header with title and close button. */
export function ModalHeader({ title, children, onClose }: { title?: string; children?: React.ReactNode; onClose: () => void }) {
  return (
    <div className="flex items-center justify-between px-5 py-4 border-b border-default shrink-0">
      {children ?? <h2 className="text-sm font-semibold text-primary">{title}</h2>}
      <button onClick={onClose} className="p-1 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

/** Scrollable modal body. */
export function ModalBody({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-4">
      {children}
    </div>
  );
}

/** Modal footer with right-aligned actions. */
export function ModalFooter({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-end gap-2 px-5 py-3 border-t border-default shrink-0">
      {children}
    </div>
  );
}
