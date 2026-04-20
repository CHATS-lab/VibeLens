export const SEVERITY_LABELS: Record<number, string> = {
  1: "Minor",
  2: "Low",
  3: "Moderate",
  4: "High",
  5: "Critical",
};

export const SEVERITY_DESCRIPTIONS: Record<number, string> = {
  1: "Minor: Small correction, resolved immediately",
  2: "Low: Needed to explain once more",
  3: "Moderate: Multiple corrections or visible frustration",
  4: "High: Had to take over or revert changes",
  5: "Critical: Gave up on the task entirely",
};

export const FRICTION_TUTORIAL = {
  title: "How does this work?",
  description: "VibeLens reviews your coding sessions to find where things went wrong: getting stuck, repeating yourself, or fixing agent mistakes. You get practical tips to avoid those issues next time.",
};

/** Convert kebab-case type_name to Title Case for display. */
export function frictionTypeLabel(typeName: string): string {
  return typeName
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function confidenceLevel(c: number): "high" | "medium" | "low" {
  if (c >= 0.7) return "high";
  if (c >= 0.4) return "medium";
  return "low";
}
