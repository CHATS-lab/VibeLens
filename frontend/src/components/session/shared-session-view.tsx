import { useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import { sessionsClient } from "../../api/sessions";
import type { Trajectory } from "../../types";
import { SessionView } from "./session-view";
import { LoadingSpinner } from "../ui/loading-spinner";

interface SharedSessionViewProps {
  shareToken: string;
}

export function SharedSessionView({ shareToken }: SharedSessionViewProps) {
  const { fetchWithToken } = useAppContext();
  const api = useMemo(() => sessionsClient(fetchWithToken), [fetchWithToken]);
  const [trajectories, setTrajectories] = useState<Trajectory[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api
      .getShare(shareToken)
      .then((data) => {
        if (!data.length) throw new Error("Share contains no session data");
        setTrajectories(data);
      })
      .catch((err: Error) => {
        // Translate HTTP 404 into a human-friendly message for revoked shares.
        setError(
          err.message.includes("404")
            ? "Share not found or has been revoked"
            : err.message,
        );
      })
      .finally(() => setLoading(false));
  }, [api, shareToken]);

  if (loading) {
    return <LoadingSpinner label="Loading shared session" />;
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-4">
        <div className="text-center bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-lg p-6 max-w-md">
          <p className="text-sm font-semibold text-rose-700 dark:text-rose-300 mb-2">Failed to load shared session</p>
          <p className="text-xs text-rose-600 dark:text-rose-400 font-mono break-all">{error}</p>
        </div>
      </div>
    );
  }

  if (!trajectories?.length) return null;

  // Render using the existing SessionView with shared data passed directly
  const sessionId = trajectories[0].session_id;
  return <SessionView sessionId={sessionId} sharedTrajectories={trajectories} shareToken={shareToken} />;
}
