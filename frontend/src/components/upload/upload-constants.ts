import type { AgentType, OSPlatform } from "../../types";

export type UploadStep = "select" | "upload" | "confirm" | "result";

// Agent metadata is fetched from GET /upload/agents at dialog open time
// (see uploadClient.agents in api/upload.ts). The frontend no longer
// hardcodes labels/descriptions — backend services/upload/agents.py is
// the single source of truth.

export const OS_OPTIONS: { platform: OSPlatform; label: string }[] = [
  { platform: "macos", label: "macOS" },
  { platform: "linux", label: "Linux" },
  { platform: "windows", label: "Windows" },
];

export const DEFAULT_AGENT: AgentType = "claude";
export const DEFAULT_OS: OSPlatform = "macos";
