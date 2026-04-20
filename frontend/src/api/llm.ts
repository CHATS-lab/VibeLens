import type { CliBackendModels, LiteLLMPreset, LLMStatus } from "../types";
import type { FetchWithToken } from "./analysis";

export interface LLMConfigurePayload {
  backend: string;
  api_key?: string;
  model?: string;
  base_url?: string;
}

export interface LLMClient {
  status: () => Promise<LLMStatus>;
  configure: (payload: LLMConfigurePayload) => Promise<void>;
  cliModels: () => Promise<Record<string, CliBackendModels>>;
  litellmPresets: () => Promise<LiteLLMPreset[]>;
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function llmClient(fetchWithToken: FetchWithToken): LLMClient {
  return {
    status: async () => jsonOrThrow(await fetchWithToken("/api/llm/status")),
    configure: async (payload) => {
      const res = await fetchWithToken("/api/llm/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
    },
    cliModels: async () => jsonOrThrow(await fetchWithToken("/api/llm/cli-models")),
    litellmPresets: async () => {
      const data = await jsonOrThrow<{ models?: LiteLLMPreset[] }>(
        await fetchWithToken("/api/llm/litellm-presets"),
      );
      return data.models ?? [];
    },
  };
}
