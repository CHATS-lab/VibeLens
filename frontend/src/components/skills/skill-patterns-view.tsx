import { ArrowUpRight, BookOpen, ChevronDown, ChevronRight, Repeat, Target } from "lucide-react";
import { useCallback, useState } from "react";
import type { StepRef, WorkflowPattern } from "../../types";
import { BulletText } from "../bullet-text";
import { Tooltip } from "../tooltip";
import { SectionHeader } from "./skill-shared";

export function PatternSection({ patterns }: { patterns: WorkflowPattern[] }) {
  return (
    <section>
      <SectionHeader
        icon={<Target className="w-5 h-5" />}
        title="How You Work"
        tooltip="Recurring habits and patterns found across your sessions"
      />
      <div className="space-y-3">
        {patterns.map((p, i) => <PatternCard key={i} pattern={p} index={i} />)}
      </div>
    </section>
  );
}

function PatternCard({ pattern, index }: { pattern: WorkflowPattern; index: number }) {
  const [expanded, setExpanded] = useState(index === 0);

  return (
    <div
      onClick={() => setExpanded(!expanded)}
      className="border border-card rounded-xl overflow-hidden cursor-pointer hover:border-hover transition-all"
    >
      <div className="px-4 py-3 space-y-2.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <Tooltip text={`Seen ${pattern.frequency}x across sessions`}>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-accent-teal-subtle text-accent-teal border border-accent-teal">
              <Repeat className="w-2.5 h-2.5" />
              {pattern.frequency}x
            </span>
          </Tooltip>
          <h6 className="text-base font-semibold text-primary">{pattern.title}</h6>
          <div className="ml-auto shrink-0">
            {expanded
              ? <ChevronDown className="w-4 h-4 text-dimmed" />
              : <ChevronRight className="w-4 h-4 text-dimmed" />}
          </div>
        </div>
        <BulletText text={pattern.description} className="text-sm text-secondary leading-relaxed" />
      </div>
      {expanded && (
        <div className="px-4 pb-3.5 space-y-2.5 border-t border-card pt-3 mx-3 mb-1">
          <StepRefList refs={pattern.example_refs} />
        </div>
      )}
    </div>
  );
}

/** Renders a list of step reference buttons with a "Reference:" label. */
export function StepRefList({ refs }: { refs: StepRef[] }) {
  if (refs.length === 0) return null;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1.5 text-sm">
        <BookOpen className="w-4 h-4 text-accent-cyan" />
        <span className="font-semibold text-accent-cyan">Reference:</span>
      </div>
      {refs.map((stepRef, i) => (
        <JumpToStepButton key={i} stepRef={stepRef} />
      ))}
    </div>
  );
}

function JumpToStepButton({ stepRef }: { stepRef: StepRef }) {
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const url = `${window.location.origin}?session=${stepRef.session_id}&step=${stepRef.start_step_id}`;
      window.open(url, "_blank");
    },
    [stepRef.session_id, stepRef.start_step_id],
  );

  return (
    <Tooltip text="Open step in session viewer">
      <button
        onClick={handleClick}
        className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-control-hover/50 text-secondary hover:bg-teal-50 dark:hover:bg-teal-900/40 hover:text-accent-teal transition font-mono border border-hover/30 hover:border-accent-teal"
      >
        {stepRef.start_step_id.slice(0, 8)}
        <ArrowUpRight className="w-3 h-3" />
      </button>
    </Tooltip>
  );
}
