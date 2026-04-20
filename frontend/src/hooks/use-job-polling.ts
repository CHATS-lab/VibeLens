import { useEffect } from "react";
import { JOB_POLL_INTERVAL_MS } from "../constants";
import type { AnalysisJobStatus } from "../types";

type FetchWithToken = (url: string, init?: RequestInit) => Promise<Response>;

interface JobPollingCallbacks {
  onCompleted: (analysisId: string) => void | Promise<void>;
  onFailed: (message: string) => void;
  onCancelled: () => void;
}

/** Poll `${apiBase}/jobs/${jobId}` until the job reaches a terminal state.
 * Callbacks fire at most once per terminal state. Errors during polling
 * are swallowed — polling is best-effort.
 */
export function useJobPolling(
  jobId: string | null,
  apiBase: string,
  fetchWithToken: FetchWithToken,
  callbacks: JobPollingCallbacks,
): void {
  const { onCompleted, onFailed, onCancelled } = callbacks;
  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetchWithToken(`${apiBase}/jobs/${jobId}`);
        if (!res.ok) return;
        const status: AnalysisJobStatus = await res.json();
        if (status.status === "completed" && status.analysis_id) {
          await onCompleted(status.analysis_id);
        } else if (status.status === "failed") {
          onFailed(status.error_message || "Analysis failed");
        } else if (status.status === "cancelled") {
          onCancelled();
        }
      } catch {
        /* best-effort */
      }
    }, JOB_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [jobId, apiBase, fetchWithToken, onCompleted, onFailed, onCancelled]);
}
