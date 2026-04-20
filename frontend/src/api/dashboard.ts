import type { DashboardStats, ToolUsageStat } from "../types";
import type { FetchWithToken } from "./analysis";

export interface DashboardFilters {
  project?: string | null;
  agent?: string | null;
}

export interface WarmingStatus {
  total: number;
  loaded: number;
  done: boolean;
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function filterParams(filters?: DashboardFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters?.project) params.set("project_path", filters.project);
  if (filters?.agent) params.set("agent_name", filters.agent);
  return params;
}

export interface DashboardClient {
  stats: (filters?: DashboardFilters, opts?: { refresh?: boolean }) => Promise<DashboardStats>;
  toolUsage: (filters?: DashboardFilters) => Promise<ToolUsageStat[]>;
  refreshSessions: () => Promise<void>;
  export: (format: "csv" | "json", filters?: DashboardFilters) => Promise<Blob>;
  warmingStatus: () => Promise<WarmingStatus | null>;
}

export function dashboardClient(fetchWithToken: FetchWithToken): DashboardClient {
  return {
    stats: async (filters, opts) => {
      const params = filterParams(filters);
      if (opts?.refresh) params.set("refresh", "true");
      const qs = params.toString();
      return jsonOrThrow(
        await fetchWithToken(`/api/analysis/dashboard${qs ? `?${qs}` : ""}`),
      );
    },
    toolUsage: async (filters) => {
      const qs = filterParams(filters).toString();
      const res = await fetchWithToken(`/api/analysis/tool-usage${qs ? `?${qs}` : ""}`);
      return res.ok ? res.json() : [];
    },
    refreshSessions: async () => {
      await fetchWithToken("/api/sessions?refresh=true");
    },
    export: async (format, filters) => {
      const params = filterParams(filters);
      params.set("format", format);
      const res = await fetchWithToken(`/api/analysis/dashboard/export?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.blob();
    },
    warmingStatus: async () => {
      const res = await fetchWithToken("/api/warming-status");
      return res.ok ? res.json() : null;
    },
  };
}
