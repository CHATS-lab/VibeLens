import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../app";
import { dashboardClient } from "../api/dashboard";
import type { DashboardStats, ToolUsageStat } from "../types";
import { errorMessage } from "../utils";

export interface DashboardCache {
  stats: DashboardStats;
  toolUsage: ToolUsageStat[];
}

interface UseDashboardDataArgs {
  cache: DashboardCache | null;
  selectedProject: string | null;
  selectedAgent: string | null;
}

interface UseDashboardDataResult {
  stats: DashboardStats | null;
  toolUsage: ToolUsageStat[];
  loading: boolean;
  error: string | null;
  refreshing: boolean;
  refresh: () => Promise<void>;
  restoreFromCache: () => void;
}

/** All data fetches for the dashboard view. Handles: initial cache hydration,
 * fallback fetch when cache is absent, on-demand refetch when filters change,
 * and manual refresh that re-scans sessions from disk.
 */
export function useDashboardData({
  cache,
  selectedProject,
  selectedAgent,
}: UseDashboardDataArgs): UseDashboardDataResult {
  const { fetchWithToken } = useAppContext();
  const api = useMemo(() => dashboardClient(fetchWithToken), [fetchWithToken]);

  const [stats, setStats] = useState<DashboardStats | null>(cache?.stats ?? null);
  const [toolUsage, setToolUsage] = useState<ToolUsageStat[]>(cache?.toolUsage ?? []);
  const [loading, setLoading] = useState(!cache);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Populate from cache when it arrives (background preload).
  useEffect(() => {
    if (!cache) return;
    if (cache.stats && !stats) {
      setStats(cache.stats);
      setLoading(false);
    }
    if (cache.toolUsage.length > 0) {
      setToolUsage(cache.toolUsage);
    }
  }, [cache, stats]);

  // Fallback fetch if cache hasn't arrived after mount.
  useEffect(() => {
    if (cache || stats || selectedProject || selectedAgent) return;
    api
      .stats()
      .then(setStats)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
    api.toolUsage().then(setToolUsage).catch(() => {});
  }, [cache, stats, api, selectedProject, selectedAgent]);

  // Refetch on filter change.
  useEffect(() => {
    if (!selectedProject && !selectedAgent) return;
    setLoading(true);
    setError(null);
    const filters = { project: selectedProject, agent: selectedAgent };
    Promise.all([api.stats(filters), api.toolUsage(filters)])
      .then(([dashData, toolData]) => {
        setStats(dashData);
        setToolUsage(toolData);
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, [api, selectedProject, selectedAgent]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      await api.refreshSessions();
      const [dashData, toolData] = await Promise.all([
        api.stats(undefined, { refresh: true }),
        api.toolUsage(),
      ]);
      setStats(dashData);
      setToolUsage(toolData);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }, [api]);

  const restoreFromCache = useCallback(() => {
    if (!cache) return;
    setStats(cache.stats);
    setToolUsage(cache.toolUsage);
  }, [cache]);

  return {
    stats,
    toolUsage,
    loading,
    error,
    refreshing,
    refresh,
    restoreFromCache,
  };
}
