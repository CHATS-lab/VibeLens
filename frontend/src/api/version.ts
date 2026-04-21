import type { FetchWithToken } from "./analysis";

export type InstallMethod = "uv" | "pip" | "npx" | "source" | "unknown";

export interface VersionInfo {
  current: string;
  latest: string | null;
  update_available: boolean;
  is_dev_build: boolean;
  install_method: InstallMethod;
  install_commands: { uv: string; pip: string; npx: string };
}

export interface VersionClient {
  get: () => Promise<VersionInfo>;
}

export function versionClient(fetchWithToken: FetchWithToken): VersionClient {
  return {
    get: async () => {
      const res = await fetchWithToken("/api/version");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
  };
}
