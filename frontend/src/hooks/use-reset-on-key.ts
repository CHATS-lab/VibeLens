import { useEffect } from "react";

/** Run `reset` whenever a monotonically increasing `key` ticks past zero.
 * Convention: parent increments the key to signal "reset"; 0 means "no-op"
 * so the reset does not run on initial mount.
 */
export function useResetOnKey(key: number, reset: () => void): void {
  useEffect(() => {
    if (key > 0) reset();
    // Intentionally depend only on `key`: we want to re-run on bumps,
    // not on every reset-callback identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
