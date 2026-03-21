import { Bot, MessageSquare, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import type { Trajectory } from "../../types";
import { CollapsiblePill } from "../collapsible-pill";
import { StepBlock } from "./message-block";

interface SubAgentBlockProps {
  trajectory: Trajectory;
  allTrajectories: Trajectory[];
}

export function SubAgentBlock({ trajectory, allTrajectories }: SubAgentBlockProps) {
  const [open, setOpen] = useState(false);

  const steps = trajectory.steps || [];
  const stepCount = steps.length;
  const toolCallCount = steps.reduce(
    (sum, s) => sum + (s.tool_calls?.length || 0),
    0,
  );

  // Find child sub-agents whose parent_trajectory_ref points to this trajectory
  const childSubAgents = useMemo(
    () =>
      allTrajectories.filter(
        (t) => t.parent_trajectory_ref?.session_id === trajectory.session_id
      ),
    [allTrajectories, trajectory.session_id]
  );

  const label = trajectory.session_id.slice(0, 12);
  const preview = `${stepCount} steps • ${toolCallCount} tools`;

  return (
    <CollapsiblePill
      open={open}
      onToggle={() => setOpen(!open)}
      icon={<Bot className="w-3.5 h-3.5" />}
      label={label}
      preview={preview}
      className="bg-violet-500/10 border-violet-500/30 text-violet-300"
    >
      <div className="border-l-2 border-violet-500/30 ml-3 pl-3 py-2 space-y-2">
        <div className="flex items-center gap-3 text-[10px] text-violet-400 px-1 pb-1">
          <span className="flex items-center gap-1">
            <MessageSquare className="w-3 h-3" />
            {stepCount}
          </span>
          <span className="flex items-center gap-1">
            <Wrench className="w-3 h-3" />
            {toolCallCount}
          </span>
        </div>
        {steps
          .filter((s) => s.source === "user" || s.source === "agent")
          .map((step) => (
            <StepBlock key={step.step_id} step={step} />
          ))}
        {childSubAgents.map((child) => (
          <SubAgentBlock
            key={child.session_id}
            trajectory={child}
            allTrajectories={allTrajectories}
          />
        ))}
      </div>
    </CollapsiblePill>
  );
}
