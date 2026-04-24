import { Check, Copy } from "lucide-react";
import { useMemo, useState } from "react";
import { useCopyFeedback } from "../../hooks/use-copy-feedback";
import { TOGGLE_ACTIVE, TOGGLE_BUTTON_BASE, TOGGLE_CONTAINER, TOGGLE_INACTIVE } from "../../styles";
import type { Mitigation } from "../../types";
import { MarkdownRenderer } from "../ui/markdown-renderer";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../ui/modal";

type ViewMode = "preview" | "code";

interface CopyAllDialogProps {
  mitigations: Mitigation[];
  onClose: () => void;
}

/** Build the bullet list shown in the dialog: `- **{TITLE}**: {ACTION}` per line. */
function buildBulletList(mitigations: Mitigation[]): string {
  const sorted = [...mitigations].sort((a, b) => b.confidence - a.confidence);
  return sorted
    .map((m) => `- **${m.title}**: ${m.action}`)
    .join("\n");
}

/**
 * Dialog listing all productivity tips as Markdown bullets. Preview mode renders
 * the markdown; Code mode is an editable textarea. The copy button copies the
 * current source text (edits from code mode are preserved across toggles).
 */
export function CopyAllDialog({ mitigations, onClose }: CopyAllDialogProps) {
  const initialContent = useMemo(() => buildBulletList(mitigations), [mitigations]);
  const [content, setContent] = useState(initialContent);
  const [mode, setMode] = useState<ViewMode>("preview");
  const { copied, copy } = useCopyFeedback();

  return (
    <Modal onClose={onClose} maxWidth="max-w-3xl">
      <ModalHeader title="Copy All Productivity Tips" onClose={onClose} />
      <ModalBody>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-dimmed">
            Paste into your agent guide (CLAUDE.md, AGENT.md, etc.). Edit in Code mode before copying.
          </p>
          <div className={`${TOGGLE_CONTAINER} w-36 shrink-0`}>
            <button
              className={`${TOGGLE_BUTTON_BASE} ${mode === "preview" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE}`}
              onClick={() => setMode("preview")}
            >
              Preview
            </button>
            <button
              className={`${TOGGLE_BUTTON_BASE} ${mode === "code" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE}`}
              onClick={() => setMode("code")}
            >
              Code
            </button>
          </div>
        </div>
        {mode === "preview" ? (
          <div className="min-h-[300px] max-h-[50vh] overflow-y-auto bg-canvas border border-card rounded-lg px-4 py-3">
            <MarkdownRenderer content={content} variant="document" />
          </div>
        ) : (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full min-h-[300px] max-h-[50vh] bg-canvas text-secondary text-xs font-mono p-4 rounded-lg border border-card focus:border-amber-600/50 focus:outline-none resize-y leading-relaxed"
            spellCheck={false}
          />
        )}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-xs text-muted hover:text-secondary border border-card hover:border-hover rounded transition"
        >
          Cancel
        </button>
        <button
          onClick={() => copy(content)}
          className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 rounded transition"
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </ModalFooter>
    </Modal>
  );
}
