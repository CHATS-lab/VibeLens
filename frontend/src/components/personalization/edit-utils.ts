import type { SkillEdit } from "../../types";

/**
 * Best-effort application of SkillEdit[] to original SKILL.md content.
 * Edits that cannot locate their old_string are silently skipped — the user
 * can fix them in the editor afterwards.
 */
export function applySkillEdits(original: string, edits: SkillEdit[]): string {
  let result = original;

  for (const edit of edits) {
    if (edit.old_string === "") {
      // Append: add new_string to the end
      if (edit.new_string) {
        result = result.trimEnd() + "\n\n" + edit.new_string;
      }
    } else if (edit.new_string === "") {
      // Delete: remove old_string
      if (edit.replace_all) {
        result = result.split(edit.old_string).join("");
      } else {
        result = result.replace(edit.old_string, "");
      }
    } else {
      // Replace: swap old_string with new_string
      if (edit.replace_all) {
        result = result.split(edit.old_string).join(edit.new_string);
      } else {
        result = result.replace(edit.old_string, edit.new_string);
      }
    }
  }

  return result;
}
