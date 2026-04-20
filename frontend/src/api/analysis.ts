import type { AnalysisJobResponse, AnalysisJobStatus, CostEstimate } from "../types";

export type FetchWithToken = (url: string, init?: RequestInit) => Promise<Response>;

/** Parse a JSON response, throwing `{ detail }` as an Error on non-OK. */
async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function postJson(
  fetchWithToken: FetchWithToken,
  url: string,
  body: unknown,
): Promise<Response> {
  return fetchWithToken(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Client for the uniform analysis API shape
 * (`/estimate`, `/`, `/history`, `/{id}`, `/jobs/{id}`, `/jobs/{id}/cancel`).
 *
 * Used by friction and all three personalization modes.
 */
export interface AnalysisClient {
  estimate: (body: unknown) => Promise<CostEstimate>;
  submit: (body: unknown) => Promise<AnalysisJobResponse>;
  history: <TMeta>() => Promise<TMeta[]>;
  load: <TResult>(analysisId: string) => Promise<TResult>;
  remove: (analysisId: string) => Promise<void>;
  jobStatus: (jobId: string) => Promise<AnalysisJobStatus>;
  cancelJob: (jobId: string) => Promise<void>;
}

export function analysisClient(
  fetchWithToken: FetchWithToken,
  baseUrl: string,
): AnalysisClient {
  return {
    estimate: async (body) =>
      readJson<CostEstimate>(await postJson(fetchWithToken, `${baseUrl}/estimate`, body)),
    submit: async (body) =>
      readJson<AnalysisJobResponse>(await postJson(fetchWithToken, baseUrl, body)),
    history: async <TMeta>() => readJson<TMeta[]>(await fetchWithToken(`${baseUrl}/history`)),
    load: async <TResult>(analysisId: string) =>
      readJson<TResult>(await fetchWithToken(`${baseUrl}/${analysisId}`)),
    remove: async (analysisId) => {
      const res = await fetchWithToken(`${baseUrl}/${analysisId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    },
    jobStatus: async (jobId) =>
      readJson<AnalysisJobStatus>(await fetchWithToken(`${baseUrl}/jobs/${jobId}`)),
    cancelJob: async (jobId) => {
      const res = await fetchWithToken(`${baseUrl}/jobs/${jobId}/cancel`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    },
  };
}
