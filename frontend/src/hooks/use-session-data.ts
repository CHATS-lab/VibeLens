import { useEffect, useMemo, useState } from "react";
import { useAppContext } from "../app";
import { sessionsClient } from "../api/sessions";
import type { FlowData, Trajectory } from "../types";

interface UseSessionDataArgs {
  sessionId: string;
  /** When provided, skip the fetch and render these trajectories directly. */
  sharedTrajectories?: Trajectory[];
  /** Only meaningful when rendering a shared view; routes flow through the
   * `/api/shares/:token/flow` endpoint. */
  shareToken?: string | null;
  /** Flow is fetched lazily the first time this flips to true. */
  loadFlow: boolean;
}

interface UseSessionDataResult {
  trajectories: Trajectory[];
  loading: boolean;
  error: string;
  sessionCost: number | null;
  flowData: FlowData | null;
  flowLoading: boolean;
}

/** All data fetches for the session detail view. Owns trajectories, cost
 * estimate, and flow data. Shared views (`sharedTrajectories` set) skip the
 * trajectories and stats fetches.
 */
export function useSessionData({
  sessionId,
  sharedTrajectories,
  shareToken,
  loadFlow,
}: UseSessionDataArgs): UseSessionDataResult {
  const { fetchWithToken } = useAppContext();
  const api = useMemo(() => sessionsClient(fetchWithToken), [fetchWithToken]);

  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sessionCost, setSessionCost] = useState<number | null>(null);
  const [flowData, setFlowData] = useState<FlowData | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);

  const isSharedView = !!sharedTrajectories;

  useEffect(() => {
    setSessionCost(null);
    setFlowData(null);

    if (sharedTrajectories) {
      setTrajectories(sharedTrajectories);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");
    setTrajectories([]);
    api
      .get(sessionId)
      .then(setTrajectories)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId, api, sharedTrajectories]);

  useEffect(() => {
    if (!sessionId || loading || isSharedView) return;
    api
      .stats(sessionId)
      .then((data) => {
        if (data?.cost_usd != null) setSessionCost(data.cost_usd);
      })
      .catch((err) => console.error("Failed to load session stats:", err));
  }, [sessionId, loading, api, isSharedView]);

  useEffect(() => {
    if (!loadFlow || flowData || flowLoading || !sessionId) return;
    setFlowLoading(true);
    api
      .flow(sessionId, isSharedView ? shareToken ?? null : null)
      .then((data) => {
        if (data) setFlowData(data);
      })
      .catch((err) => console.error("Failed to load flow data:", err))
      .finally(() => setFlowLoading(false));
  }, [loadFlow, flowData, flowLoading, sessionId, api, isSharedView, shareToken]);

  return { trajectories, loading, error, sessionCost, flowData, flowLoading };
}
