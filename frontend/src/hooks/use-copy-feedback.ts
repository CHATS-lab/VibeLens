import { useCallback, useRef, useState } from "react";
import { copyToClipboard } from "../utils";
import { COPY_FEEDBACK_MS } from "../constants";

export type CopyState = "idle" | "copied" | "failed";

/** Copy text to the clipboard and expose a short-lived feedback state.
 * After `COPY_FEEDBACK_MS` the state reverts to "idle".
 */
export function useCopyFeedback() {
  const [state, setState] = useState<CopyState>("idle");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = useCallback(async (text: string) => {
    const ok = await copyToClipboard(text);
    setState(ok ? "copied" : "failed");
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setState("idle"), COPY_FEEDBACK_MS);
    return ok;
  }, []);

  return { state, copy, copied: state === "copied", failed: state === "failed" };
}
