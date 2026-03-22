import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { Trajectory } from "../../types";
import { SessionView } from "./session-view";

interface SharedSessionViewProps {
  shareToken: string;
}

export function SharedSessionView({ shareToken }: SharedSessionViewProps) {
  const { fetchWithToken } = useAppContext();
  const [trajectories, setTrajectories] = useState<Trajectory[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    fetchWithToken(`/api/shares/${shareToken}`)
      .then((res) => {
        if (!res.ok) throw new Error(res.status === 404 ? "Share not found or has been revoked" : `Failed to load: ${res.status}`);
        return res.json();
      })
      .then((data: Trajectory[]) => {
        if (!data.length) throw new Error("Share contains no session data");
        setTrajectories(data);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [shareToken, fetchWithToken]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-cyan-500 animate-spin mx-auto mb-2" />
          <p className="text-sm text-zinc-400">Loading shared session...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-4">
        <div className="text-center bg-rose-900/20 border border-rose-800 rounded-lg p-6 max-w-md">
          <p className="text-sm font-semibold text-rose-300 mb-2">Failed to load shared session</p>
          <p className="text-xs text-rose-400 font-mono break-all">{error}</p>
        </div>
      </div>
    );
  }

  if (!trajectories?.length) return null;

  // Render using the existing SessionView with shared data passed directly
  const sessionId = trajectories[0].session_id;
  return <SessionView sessionId={sessionId} sharedTrajectories={trajectories} shareToken={shareToken} />;
}
