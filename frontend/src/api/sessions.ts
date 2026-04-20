import type { FlowData, Trajectory } from "../types";
import type { FetchWithToken } from "./analysis";

interface SessionStats {
  cost_usd?: number | null;
}

export interface ShareCreateResponse {
  session_id: string;
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface SessionsClient {
  get: (sessionId: string) => Promise<Trajectory[]>;
  search: (query: string, sources: string[]) => Promise<string[]>;
  stats: (sessionId: string) => Promise<SessionStats | null>;
  flow: (sessionId: string, shareToken?: string | null) => Promise<FlowData | null>;
  createShare: (sessionId: string) => Promise<ShareCreateResponse>;
  getShare: (shareToken: string) => Promise<Trajectory[]>;
  exportJson: (sessionId: string) => Promise<Blob>;
}

export function sessionsClient(fetchWithToken: FetchWithToken): SessionsClient {
  return {
    get: async (sessionId) => jsonOrThrow(await fetchWithToken(`/api/sessions/${sessionId}`)),
    search: async (query, sources) => {
      const params = new URLSearchParams({ q: query, sources: sources.join(",") });
      return jsonOrThrow(await fetchWithToken(`/api/sessions/search?${params}`));
    },
    stats: async (sessionId) => {
      const res = await fetchWithToken(`/api/analysis/sessions/${sessionId}/stats`);
      return res.ok ? res.json() : null;
    },
    flow: async (sessionId, shareToken) => {
      const url = shareToken
        ? `/api/shares/${shareToken}/flow`
        : `/api/sessions/${sessionId}/flow`;
      const res = await fetchWithToken(url);
      return res.ok ? res.json() : null;
    },
    createShare: async (sessionId) => {
      const res = await fetchWithToken("/api/shares", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`Failed to create share: ${res.status}`);
      return res.json();
    },
    getShare: async (shareToken) =>
      jsonOrThrow(await fetchWithToken(`/api/shares/${shareToken}`)),
    exportJson: async (sessionId) => {
      const res = await fetchWithToken(`/api/sessions/${sessionId}/export`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.blob();
    },
  };
}
