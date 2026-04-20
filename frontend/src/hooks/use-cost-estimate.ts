import { useCallback, useState } from "react";
import type { CostEstimate } from "../types";

type FetchWithToken = (url: string, init?: RequestInit) => Promise<Response>;

interface UseCostEstimateResult {
  estimate: CostEstimate | null;
  estimating: boolean;
  requestEstimate: (url: string, body: unknown) => Promise<boolean>;
  clearEstimate: () => void;
}

/** Manage the "POST /estimate -> show dialog -> confirm or cancel" flow
 * shared by analysis panels.
 *
 * Returns `true` from `requestEstimate` on success (an estimate was fetched
 * and stored). On failure, the hook's `estimating` flag resets and callers
 * receive `false` along with the thrown error from the response body so they
 * can surface it in their own error UI.
 */
export function useCostEstimate(
  fetchWithToken: FetchWithToken,
  onError: (message: string) => void,
): UseCostEstimateResult {
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);

  const requestEstimate = useCallback(
    async (url: string, body: unknown): Promise<boolean> => {
      setEstimating(true);
      try {
        const res = await fetchWithToken(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(data?.detail || `HTTP ${res.status}`);
        }
        setEstimate(await res.json());
        return true;
      } catch (err) {
        onError(err instanceof Error ? err.message : String(err));
        return false;
      } finally {
        setEstimating(false);
      }
    },
    [fetchWithToken, onError],
  );

  const clearEstimate = useCallback(() => setEstimate(null), []);

  return { estimate, estimating, requestEstimate, clearEstimate };
}
