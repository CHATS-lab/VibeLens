import type { FetchWithToken } from "./analysis";

export interface UploadCommands {
  command: string;
  description: string;
}

export interface UploadClient {
  commands: (agentType: string, osPlatform: string) => Promise<UploadCommands>;
}

export function uploadClient(fetchWithToken: FetchWithToken): UploadClient {
  return {
    commands: async (agentType, osPlatform) => {
      const res = await fetchWithToken(
        `/api/upload/commands?agent_type=${agentType}&os_platform=${osPlatform}`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
  };
}
