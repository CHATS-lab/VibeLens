/**
 * Flow layout engine — converts Steps + FlowData into structured card data.
 *
 * User prompts are treated as **anchors** — standalone dividers between
 * phases.  Only agent steps (with tool calls or text) participate in
 * phase grouping.  The output `sections` array interleaves user anchors
 * and phase groups in chronological order for the diagram to render.
 */

import type { Step, ToolDependencyGraph, PhaseSegment } from "../../types";
import { extractMessageText } from "../../utils";
import { LABEL_MAX_LENGTH } from "../../constants";

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
  promptIndex: number;
  isAutoPrompt: boolean;
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

/** A section in the flow diagram — either a user anchor or a phase group. */
export type FlowSection =
  | { type: "anchor"; data: FlowUserCardData }
  | { type: "phase"; data: FlowPhaseGroup };

export interface ToolRelation {
  targetToolCallId: string;
  relation: string;
  sharedResource?: string;
}

export interface FlowResult {
  /** Phase groups (agent-only) for the nav panel. */
  phases: FlowPhaseGroup[];
  /** Interleaved anchors + phases for the diagram. */
  sections: FlowSection[];
  dependencies: Map<string, ToolRelation[]>;
}

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
  TaskOutput: "task",
  TaskStop: "task",
  TodoWrite: "task",
  TodoRead: "task",
  AskUserQuestion: "interact",
  AskUser: "interact",
  EnterPlanMode: "interact",
  ExitPlanMode: "interact",
  EnterWorktree: "interact",
  NotebookRead: "file_read",
  LS: "search",
  ls: "search",
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
  const { userCards, agentCards } = buildCards(steps);
  const phaseGroups = assignAgentCardsToPhases(agentCards, phases);
  const sections = interleaveSections(userCards, phaseGroups);
  const dependencies = buildDependencyMap(toolGraph);
  return { phases: phaseGroups, sections, dependencies };
}

interface CardSplit {
  userCards: FlowUserCardData[];
  agentCards: FlowCard[];
}

function buildCards(steps: Step[]): CardSplit {
  const userCards: FlowUserCardData[] = [];
  const agentCards: FlowCard[] = [];
  let globalStepIdx = 0;
  let promptNumber = 0;

  for (const step of steps) {
    const stepIdx = globalStepIdx++;

    if (step.source === "user") {
      const text = extractMessageText(step.message);
      if (!text) continue;
      // Skip skill outputs entirely but keep auto-prompts (plan mode, etc.)
      if (step.extra?.is_skill_output) continue;
      const isAuto = !!step.extra?.is_auto_prompt;
      promptNumber++;
      userCards.push({
        id: `user-${step.step_id}`,
        label: truncateLabel(text, LABEL_MAX_LENGTH),
        detail: text,
        stepIndex: stepIdx,
        promptIndex: promptNumber,
        isAutoPrompt: isAuto,
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

      agentCards.push({
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

  return { userCards, agentCards };
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

/** Assign only agent cards to phase groups. User cards are excluded. */
function assignAgentCardsToPhases(
  agentCards: FlowCard[],
  phases: PhaseSegment[]
): FlowPhaseGroup[] {
  if (phases.length === 0) {
    if (agentCards.length === 0) return [];
    const { toolCount, dominantCategory } = computePhaseSummary(agentCards);
    return [{ phase: "mixed", cards: agentCards, toolCount, dominantCategory }];
  }

  const groups: FlowPhaseGroup[] = [];
  const assignedIndices = new Set<number>();

  for (const seg of phases) {
    const segCards = agentCards.filter((c) => {
      const idx = c.data.stepIndex;
      return idx >= seg.start_index && idx <= seg.end_index;
    });
    if (segCards.length > 0) {
      const { toolCount, dominantCategory } = computePhaseSummary(segCards);
      groups.push({ phase: seg.phase, cards: segCards, toolCount, dominantCategory });
      segCards.forEach((c) => assignedIndices.add(c.data.stepIndex));
    }
  }

  // Unassigned agent cards go into "mixed"
  const uncovered = agentCards.filter((c) => !assignedIndices.has(c.data.stepIndex));
  if (uncovered.length > 0) {
    const { toolCount, dominantCategory } = computePhaseSummary(uncovered);
    groups.push({ phase: "mixed", cards: uncovered, toolCount, dominantCategory });
  }

  return groups;
}

/**
 * Interleave user anchors and phase groups in chronological order.
 *
 * A user anchor appears before the phase group whose first card has a
 * stepIndex greater than the anchor's stepIndex.  This makes user
 * prompts natural dividers between phases.
 */
function interleaveSections(
  userCards: FlowUserCardData[],
  phaseGroups: FlowPhaseGroup[]
): FlowSection[] {
  type Entry = { stepIndex: number; section: FlowSection };
  const entries: Entry[] = [];

  for (const user of userCards) {
    entries.push({
      stepIndex: user.stepIndex,
      section: { type: "anchor", data: user },
    });
  }

  // Split phase groups at user anchor boundaries
  for (const group of phaseGroups) {
    const sortedCards = [...group.cards].sort(
      (a, b) => a.data.stepIndex - b.data.stepIndex
    );
    if (sortedCards.length === 0) continue;

    const firstIdx = sortedCards[0].data.stepIndex;
    const lastIdx = sortedCards[sortedCards.length - 1].data.stepIndex;

    // Find anchor stepIndices that fall within this group's range
    const splitPoints = userCards
      .map((u) => u.stepIndex)
      .filter((idx) => idx > firstIdx && idx <= lastIdx)
      .sort((a, b) => a - b);

    if (splitPoints.length === 0) {
      // No anchors bisect this group — emit as-is
      entries.push({ stepIndex: firstIdx, section: { type: "phase", data: group } });
    } else {
      // Split cards into sub-groups at anchor boundaries
      let currentCards: FlowCard[] = [];
      let splitIdx = 0;

      for (const card of sortedCards) {
        // If this card's stepIndex crosses the next split point, flush the sub-group
        while (
          splitIdx < splitPoints.length &&
          card.data.stepIndex >= splitPoints[splitIdx]
        ) {
          if (currentCards.length > 0) {
            const { toolCount, dominantCategory } = computePhaseSummary(currentCards);
            entries.push({
              stepIndex: currentCards[0].data.stepIndex,
              section: {
                type: "phase",
                data: { phase: group.phase, cards: currentCards, toolCount, dominantCategory },
              },
            });
          }
          currentCards = [];
          splitIdx++;
        }
        currentCards.push(card);
      }

      // Flush remaining cards
      if (currentCards.length > 0) {
        const { toolCount, dominantCategory } = computePhaseSummary(currentCards);
        entries.push({
          stepIndex: currentCards[0].data.stepIndex,
          section: {
            type: "phase",
            data: { phase: group.phase, cards: currentCards, toolCount, dominantCategory },
          },
        });
      }
    }
  }

  // Sort by stepIndex; anchors before phases at the same index
  entries.sort((a, b) => {
    if (a.stepIndex !== b.stepIndex) return a.stepIndex - b.stepIndex;
    return a.section.type === "anchor" ? -1 : 1;
  });

  return entries.map((e) => e.section);
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
