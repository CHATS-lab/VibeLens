import type { SkillEdit } from "../../types";

const REMOVE_KINDS = new Set(["remove_instruction", "remove_tool"]);
const REPLACE_KINDS = new Set(["replace_instruction", "update_description"]);
const APPEND_KINDS = new Set(["add_instruction", "add_tool"]);

/**
 * Best-effort application of SkillEdit[] to original SKILL.md content.
 * Edits that cannot locate their target are silently skipped — the user
 * can fix them in the editor afterwards.
 */
export function applySkillEdits(original: string, edits: SkillEdit[]): string {
  let result = original;

  for (const edit of edits) {
    if (REMOVE_KINDS.has(edit.kind)) {
      if (result.includes(edit.target)) {
        result = result.replace(edit.target, "");
      }
    } else if (REPLACE_KINDS.has(edit.kind) && edit.replacement) {
      if (result.includes(edit.target)) {
        result = result.replace(edit.target, edit.replacement);
      }
    } else if (APPEND_KINDS.has(edit.kind) && edit.replacement) {
      result = result.trimEnd() + "\n\n" + edit.replacement;
    }
  }

  return result;
}
