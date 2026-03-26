import { Check, Loader2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Modal } from "../modal";

interface SkillEditorDialogProps {
  mode: "create" | "edit";
  initialName: string;
  initialContent: string;
  onSave: (name: string, content: string) => void;
  onCancel: () => void;
  saving: boolean;
}

export function SkillEditorDialog({
  mode,
  initialName,
  initialContent,
  onSave,
  onCancel,
  saving,
}: SkillEditorDialogProps) {
  const [name, setName] = useState(initialName);
  const [content, setContent] = useState(initialContent);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isCreate = mode === "create";
  const nameValid = /^[a-z0-9]+(-[a-z0-9]+)*$/.test(name);
  const contentValid = content.trim().length > 0;
  const canSave = nameValid && contentValid && !saving;

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <Modal onClose={onCancel} maxWidth="max-w-3xl">
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
        <h2 className="text-sm font-semibold text-zinc-100">
          {isCreate ? "Create New Skill" : `Edit: ${initialName}`}
        </h2>
        <button onClick={onCancel} className="text-zinc-500 hover:text-zinc-300 transition">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="px-5 py-4 flex-1 min-h-0 flex flex-col gap-3 overflow-hidden">
        {isCreate && (
          <div>
            <label className="block text-xs text-zinc-400 mb-1">
              Skill name <span className="text-zinc-600">(kebab-case)</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value.toLowerCase())}
              placeholder="my-new-skill"
              className={`w-full px-3 py-1.5 text-sm font-mono rounded bg-zinc-800 border text-zinc-100 outline-none focus:ring-1 transition ${
                name && !nameValid
                  ? "border-red-500/50 focus:ring-red-500/30"
                  : "border-zinc-700 focus:ring-teal-500/30 focus:border-teal-600"
              }`}
            />
            {name && !nameValid && (
              <p className="text-[10px] text-red-400 mt-1">
                Lowercase letters, numbers, and hyphens only
              </p>
            )}
          </div>
        )}
        <div className="flex-1 min-h-0 flex flex-col">
          <label className="block text-xs text-zinc-400 mb-1">SKILL.md content</label>
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={`---\ndescription: What this skill does\nallowed-tools: Read, Edit, Bash\ntags: [development, automation]\n---\n\n# Instructions\n\n...`}
            className="flex-1 min-h-[300px] w-full px-3 py-2 text-sm font-mono rounded bg-zinc-800 border border-zinc-700 text-zinc-100 outline-none focus:ring-1 focus:ring-teal-500/30 focus:border-teal-600 resize-none transition"
            spellCheck={false}
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 px-5 py-3 border-t border-zinc-800 shrink-0">
        <button
          onClick={onCancel}
          disabled={saving}
          className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={() => canSave && onSave(name, content)}
          disabled={!canSave}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-teal-600 hover:bg-teal-500 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          {isCreate ? "Create" : "Save"}
        </button>
      </div>
    </Modal>
  );
}
