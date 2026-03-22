/**
 * Flow layout engine — converts Steps + FlowData into structured card data.
 *
 * Produces phase-grouped cards (user prompts + agent responses with embedded
 * tool chips) and a dependency map for hover highlighting. No x/y positioning
 * needed — the FlowDiagram component uses DOM/CSS layout.
 */

import type { Step, ToolDependencyGraph, PhaseSegment } from "../../types";
import { extractMessageText } from "../../utils";

export interface FlowToolChip {
  id: string;
  name: string;
  category: string;
  detail: string;
  toolCallId: string;
}

export interface FlowAgentCardData {
  id: string;
  label: string;
  detail: string;
  stepIndex: number;
  tools: FlowToolChip[];
}

export interface FlowUserCardData {
  id: string;
  label: string;
  detail: string;
  stepIndex: number;
}

export type FlowCard =
  | { type: "user"; data: FlowUserCardData }
  | { type: "agent"; data: FlowAgentCardData };

export interface FlowPhaseGroup {
  phase: string;
  cards: FlowCard[];
  toolCount: number;
  dominantCategory: string;
}

export interface ToolRelation {
  targetToolCallId: string;
  relation: string;
  sharedResource?: string;
}

export interface FlowResult {
  phases: FlowPhaseGroup[];
  dependencies: Map<string, ToolRelation[]>;
}

const LABEL_MAX_LENGTH = 120;

const TOOL_CATEGORY_MAP: Record<string, string> = {
  Read: "file_read",
  read_file: "file_read",
  cat: "file_read",
  Glob: "search",
  glob: "search",
  Grep: "search",
  grep: "search",
  find: "search",
  Edit: "file_write",
  Write: "file_write",
  write_file: "file_write",
  NotebookEdit: "file_write",
  MultiEdit: "file_write",
  apply_patch: "file_write",
  "apply-patch": "file_write",
  Bash: "shell",
  bash: "shell",
  shell: "shell",
  execute_command: "shell",
  WebSearch: "web",
  WebFetch: "web",
  web_search: "web",
  Agent: "agent",
  Task: "agent",
  Skill: "agent",
  TaskCreate: "task",
  TaskUpdate: "task",
  TaskList: "task",
  TaskGet: "task",
};

function truncateLabel(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 1) + "\u2026";
}

function formatToolArgs(args: unknown): string {
  if (!args) return "";
  if (typeof args === "string") return args.slice(0, 300);
  try {
    return JSON.stringify(args, null, 2).slice(0, 400);
  } catch {
    return String(args).slice(0, 300);
  }
}

/** Build structured flow data from steps and analysis results. */
export function computeFlow(
  steps: Step[],
  toolGraph: ToolDependencyGraph | null,
  phases: PhaseSegment[]
): FlowResult {
  const cards = buildCards(steps);
  const phaseGroups = assignCardsToPhases(cards, phases);
  const dependencies = buildDependencyMap(toolGraph);
  return { phases: phaseGroups, dependencies };
}

function buildCards(steps: Step[]): FlowCard[] {
  const cards: FlowCard[] = [];
  let globalStepIdx = 0;

  for (const step of steps) {
    const stepIdx = globalStepIdx++;

    if (step.source === "user") {
      const text = extractMessageText(step.message);
      if (!text) continue;
      cards.push({
        type: "user",
        data: {
          id: `user-${step.step_id}`,
          label: truncateLabel(text, LABEL_MAX_LENGTH),
          detail: text,
          stepIndex: stepIdx,
        },
      });
    }

    if (step.source === "agent") {
      const text = extractMessageText(step.message);
      const hasTools = step.tool_calls.length > 0;
      if (!text && !hasTools) continue;

      const tools: FlowToolChip[] = step.tool_calls.map((tc) => ({
        id: `tool-${tc.tool_call_id}`,
        name: tc.function_name,
        category: TOOL_CATEGORY_MAP[tc.function_name] || "other",
        detail: `${tc.function_name}\n${formatToolArgs(tc.arguments)}`,
        toolCallId: tc.tool_call_id,
      }));

      cards.push({
        type: "agent",
        data: {
          id: `agent-${step.step_id}`,
          label: text ? truncateLabel(text, LABEL_MAX_LENGTH) : "Agent processing\u2026",
          detail: text || "(tool calls only)",
          stepIndex: stepIdx,
          tools,
        },
      });
    }
  }

  return cards;
}

function computePhaseSummary(cards: FlowCard[]): { toolCount: number; dominantCategory: string } {
  const categoryCounts = new Map<string, number>();
  let toolCount = 0;
  for (const card of cards) {
    if (card.type === "agent") {
      for (const tool of card.data.tools) {
        toolCount++;
        categoryCounts.set(tool.category, (categoryCounts.get(tool.category) || 0) + 1);
      }
    }
  }
  let dominantCategory = "other";
  let maxCount = 0;
  for (const [cat, count] of categoryCounts) {
    if (count > maxCount) {
      maxCount = count;
      dominantCategory = cat;
    }
  }
  return { toolCount, dominantCategory };
}

function assignCardsToPhases(
  cards: FlowCard[],
  phases: PhaseSegment[]
): FlowPhaseGroup[] {
  if (phases.length === 0) {
    if (cards.length === 0) return [];
    const { toolCount, dominantCategory } = computePhaseSummary(cards);
    return [{ phase: "mixed", cards, toolCount, dominantCategory }];
  }

  const groups: FlowPhaseGroup[] = [];
  const assignedIndices = new Set<number>();

  for (const seg of phases) {
    const segCards = cards.filter((c) => {
      const idx = c.data.stepIndex;
      return idx >= seg.start_index && idx <= seg.end_index;
    });
    if (segCards.length > 0) {
      const { toolCount, dominantCategory } = computePhaseSummary(segCards);
      groups.push({ phase: seg.phase, cards: segCards, toolCount, dominantCategory });
      segCards.forEach((c) => assignedIndices.add(c.data.stepIndex));
    }
  }

  // Unassigned cards go into "mixed"
  const uncovered = cards.filter((c) => !assignedIndices.has(c.data.stepIndex));
  if (uncovered.length > 0) {
    const { toolCount, dominantCategory } = computePhaseSummary(uncovered);
    groups.push({ phase: "mixed", cards: uncovered, toolCount, dominantCategory });
  }

  return groups;
}

function buildDependencyMap(
  toolGraph: ToolDependencyGraph | null
): Map<string, ToolRelation[]> {
  const map = new Map<string, ToolRelation[]>();
  if (!toolGraph) return map;

  for (const edge of toolGraph.edges) {
    if (edge.relation === "sequential") continue;
    const existing = map.get(edge.source_tool_call_id) || [];
    existing.push({
      targetToolCallId: edge.target_tool_call_id,
      relation: edge.relation,
      sharedResource: edge.shared_resource || undefined,
    });
    map.set(edge.source_tool_call_id, existing);
  }

  return map;
}
