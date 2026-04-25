import { useMemo, useState } from "react";
import { TOGGLE_ACTIVE, TOGGLE_BUTTON_BASE, TOGGLE_CONTAINER, TOGGLE_INACTIVE } from "../../styles";
import type { Mitigation } from "../../types";
import { CopyButton } from "../ui/copy-button";
import { MarkdownRenderer } from "../ui/markdown-renderer";
import { Modal, ModalBody, ModalHeader } from "../ui/modal";

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

  return (
    <Modal onClose={onClose} maxWidth="max-w-3xl">
      <ModalHeader onClose={onClose}>
        <h2 className="text-lg font-semibold text-primary">Copy All Productivity Tips</h2>
      </ModalHeader>
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
        <div className="group relative h-[420px] bg-canvas border border-card rounded-lg overflow-hidden">
          {mode === "preview" ? (
            <div className="h-full overflow-y-auto px-4 py-3">
              <MarkdownRenderer content={content} variant="document" />
            </div>
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full h-full bg-canvas text-secondary text-xs font-mono p-4 focus:outline-none resize-none leading-relaxed"
              spellCheck={false}
            />
          )}
          <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity bg-panel border border-card rounded shadow-sm">
            <CopyButton text={content} />
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}
