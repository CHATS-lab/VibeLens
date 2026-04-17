import {
  AlertTriangle,
  ArrowUpRight,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  Footprints,
  Shield,
  Zap,
} from "lucide-react";
import { useCallback, useState } from "react";
import type { FrictionCost, FrictionType } from "../../types";
import { formatDuration, formatTokens } from "../../utils";
import { SEVERITY_COLORS } from "../../styles";
import { Tooltip } from "../ui/tooltip";
import { BulletText } from "../ui/bullet-text";
import { SEVERITY_DESCRIPTIONS, SEVERITY_LABELS, frictionTypeLabel } from "./friction-constants";

export function FrictionTypesSection({ frictionTypes }: { frictionTypes: FrictionType[] }) {
  const sorted = [...frictionTypes].sort((a, b) => b.severity - a.severity);

  return (
    <div>
      <Tooltip text="Moments where things slowed you down or went off track">
        <div className="flex items-center gap-2 mb-3 cursor-help">
          <span className="text-accent-amber"><AlertTriangle className="w-5 h-5" /></span>
          <h3 className="text-lg font-semibold text-primary">What Went Wrong</h3>
        </div>
      </Tooltip>
      <div className="space-y-3">
        {sorted.map((ft) => (
          <FrictionTypeCard key={ft.type_name} frictionType={ft} />
        ))}
      </div>
    </div>
  );
}

export function FrictionTypeCard({ frictionType }: { frictionType: FrictionType }) {
  const [expanded, setExpanded] = useState(false);
  const label = frictionTypeLabel(frictionType.type_name);

  return (
    <div
      onClick={() => setExpanded((v) => !v)}
      className="border border-card rounded-xl overflow-hidden cursor-pointer hover:border-hover transition-all"
    >
      <div className="px-4 py-3 space-y-2.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <SeverityBadge severity={frictionType.severity} />
          <h6 className="text-base font-semibold text-primary">{label}</h6>
          <div className="ml-auto shrink-0">
            {expanded
              ? <ChevronDown className="w-4 h-4 text-dimmed" />
              : <ChevronRight className="w-4 h-4 text-dimmed" />}
          </div>
        </div>
        <BulletText text={frictionType.description} className="text-sm text-secondary leading-relaxed" />
      </div>
      {expanded && (
        <div className="px-4 pb-3.5 space-y-2.5 border-t border-card pt-3 mx-3 mb-1">
          <CostBadges cost={frictionType.friction_cost} />
          <FrictionRefList refs={frictionType.example_refs} />
        </div>
      )}
    </div>
  );
}

export function FrictionRefList({ refs }: { refs: FrictionType["example_refs"] }) {
  if (refs.length === 0) return null;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1.5 text-sm">
        <BookOpen className="w-4 h-4 text-accent-cyan" />
        <span className="font-semibold text-accent-cyan">Reference:</span>
      </div>
      {refs.map((ref, i) => (
        <FrictionStepButton key={`${ref.session_id}-${ref.start_step_id}-${i}`} ref_={ref} />
      ))}
    </div>
  );
}

export function FrictionStepButton({ ref_ }: { ref_: FrictionType["example_refs"][number] }) {
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const url = `${window.location.origin}?session=${ref_.session_id}&step=${ref_.start_step_id}`;
      window.open(url, "_blank");
    },
    [ref_.session_id, ref_.start_step_id],
  );

  return (
    <Tooltip text="Open step in session viewer">
      <button
        onClick={handleClick}
        className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-control-hover/50 text-secondary hover:bg-amber-50 dark:hover:bg-amber-900/40 hover:text-accent-amber transition font-mono border border-hover/30 hover:border-accent-amber"
      >
        {ref_.start_step_id.slice(0, 8)}
        <ArrowUpRight className="w-3 h-3" />
      </button>
    </Tooltip>
  );
}

export function CostBadges({ cost }: { cost: FrictionCost }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-1.5 text-sm">
        <Zap className="w-4 h-4 text-accent-amber" />
        <span className="font-semibold text-accent-amber">Impact:</span>
      </div>
      <Tooltip text="Steps affected by this issue">
        <span className="inline-flex items-center gap-1.5 text-sm text-muted cursor-help">
          <Footprints className="w-4 h-4 text-rose-600 dark:text-rose-400" />
          {cost.affected_steps} step{cost.affected_steps !== 1 ? "s" : ""}
        </span>
      </Tooltip>
      {cost.affected_time_seconds != null && (
        <Tooltip text="Duration affected">
          <span className="inline-flex items-center gap-1.5 text-sm text-muted cursor-help">
            <Clock className="w-4 h-4 text-sky-600 dark:text-sky-400" />
            {formatDuration(cost.affected_time_seconds)}
          </span>
        </Tooltip>
      )}
      {cost.affected_tokens != null && (
        <Tooltip text="Tokens affected">
          <span className="inline-flex items-center gap-1.5 text-sm text-muted cursor-help">
            <Coins className="w-4 h-4 text-accent-amber" />
            {formatTokens(cost.affected_tokens)}
          </span>
        </Tooltip>
      )}
    </div>
  );
}

export function SeverityBadge({ severity }: { severity: number }) {
  const colorClass = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS[3];
  const label = SEVERITY_LABELS[severity] ?? "Unknown";
  return (
    <Tooltip text={SEVERITY_DESCRIPTIONS[severity] ?? "Impact severity rating"}>
      <span className={`inline-flex items-center justify-center gap-1.5 min-w-[6.5rem] px-2.5 py-1 rounded text-sm font-medium border shrink-0 ${colorClass}`}>
        <Shield className="w-4 h-4" />
        {label}
      </span>
    </Tooltip>
  );
}
