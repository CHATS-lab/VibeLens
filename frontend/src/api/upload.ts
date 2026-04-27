import type { FetchWithToken } from "./analysis";

export interface UploadCommands {
  command: string;
  description: string;
}

export interface AgentSpec {
  agent_type: string;
  display_name: string;
  description: string;
  source: "local_zip" | "external_export";
  user_facing: boolean;
  commands: Record<string, { command: string; output: string }>;
  external_instructions: string[];
}

export interface UploadClient {
  agents: () => Promise<AgentSpec[]>;
}

export function uploadClient(fetchWithToken: FetchWithToken): UploadClient {
  return {
    agents: async () => {
      const res = await fetchWithToken("/api/upload/agents");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      return payload.agents as AgentSpec[];
    },
  };
}
