export interface TourStep {
  id: string;
  target: string;
  title: string;
  content: string;
  placement: "right" | "bottom" | "left";
  icon: string;
  mode?: "demo";
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    target: "sidebar-header",
    title: "Welcome to VibeLens",
    content:
      "See what your coding agents are doing. Browse conversations from Claude Code, Codex, Gemini, and other agent CLIs.",
    placement: "right",
    icon: "eye",
  },
  {
    id: "sessions",
    target: "session-list",
    title: "Your Sessions",
    content:
      "Your agent sessions show up here automatically. Use the search bar, filter by agent, or group by project.",
    placement: "right",
    icon: "list",
  },
  {
    id: "view-modes",
    target: "view-modes",
    title: "Three Ways to Read",
    content:
      "Concise shows only the highlights. Detail shows every step. Workflow breaks sessions into phases with tool-call patterns.",
    placement: "bottom",
    icon: "layout",
  },
  {
    id: "dashboard",
    target: "dashboard-tab",
    title: "Analytics Dashboard",
    content:
      "Stats across all your sessions: activity heatmaps, token usage, tool distribution, and cost breakdown. No API key needed.",
    placement: "bottom",
    icon: "bar-chart",
  },
  {
    id: "ai-tabs",
    target: "ai-tabs",
    title: "AI-Powered Insights",
    content:
      "Productivity Tips spots friction and wasted effort. Personalization finds reusable skills. Both need an API key, which you can set up later.",
    placement: "bottom",
    icon: "sparkles",
  },
  {
    id: "upload",
    target: "upload-button",
    title: "Upload Your Sessions",
    content:
      "Click Upload to add your own agent sessions. Pick your agent type, run a quick command, and drag in the ZIP file.",
    placement: "right",
    icon: "upload",
    mode: "demo",
  },
];

export const TOUR_STORAGE_KEY = "vibelens-onboarding-seen";

export function getStepsForMode(appMode: string): TourStep[] {
  return TOUR_STEPS.filter((step) => !step.mode || step.mode === appMode);
}

export function hasSeenTour(): boolean {
  return localStorage.getItem(TOUR_STORAGE_KEY) === "true";
}

export function markTourSeen(): void {
  localStorage.setItem(TOUR_STORAGE_KEY, "true");
}
