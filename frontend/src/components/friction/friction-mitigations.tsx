import {
  ChevronDown,
  ChevronRight,
  Lightbulb,
  Target,
} from "lucide-react";
import { useState } from "react";
import type { FrictionType, Mitigation } from "../../types";
import { Tooltip } from "../ui/tooltip";
import { BulletText } from "../ui/bullet-text";
import { CopyButton } from "../ui/copy-button";
import { confidenceLevel, frictionTypeLabel } from "./friction-constants";
import { FrictionRefList } from "./friction-types";

export function MitigationsSection({ mitigations, frictionTypes }: { mitigations: Mitigation[]; frictionTypes: FrictionType[] }) {
  const sorted = [...mitigations].sort((a, b) => b.confidence - a.confidence);

  return (
    <div>
      <Tooltip text="Concrete steps you can take to avoid these issues in the future">
        <div className="flex items-center gap-2 mb-3 cursor-help">
          <span className="text-accent-amber"><Lightbulb className="w-5 h-5" /></span>
          <h3 className="text-xl font-semibold text-primary">Productivity Tips</h3>
        </div>
      </Tooltip>
      <div className="space-y-3">
        {sorted.map((m) => (
          <MitigationCard key={m.title} mitigation={m} frictionTypes={frictionTypes} />
        ))}
      </div>
    </div>
  );
}

export function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const level = confidenceLevel(confidence);
  const barColor = level === "high" ? "bg-amber-500" : level === "medium" ? "bg-amber-500" : "bg-control-hover";
  const textColor = level === "high" ? "text-accent-amber" : level === "medium" ? "text-accent-amber" : "text-dimmed";

  return (
    <Tooltip text={`${pct}% confidence`}>
      <div className="flex items-center gap-2 cursor-help">
        <div className="w-16 h-1.5 rounded-full bg-control-hover/60 overflow-hidden">
          <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-xs font-semibold ${textColor} tabular-nums`}>{pct}%</span>
      </div>
    </Tooltip>
  );
}

export function MitigationCard({ mitigation, frictionTypes }: { mitigation: Mitigation; frictionTypes: FrictionType[] }) {
  const [rationaleExpanded, setRationaleExpanded] = useState(false);
  const [typesExpanded, setTypesExpanded] = useState(false);

  const addressedTypes = mitigation.addressed_friction_types ?? [];
  const matchedTypes = frictionTypes.filter((ft) =>
    addressedTypes.includes(ft.type_name)
  );

  return (
    <div className="border border-default rounded-xl bg-subtle overflow-hidden">
      {/* Header: Title + Confidence (left) | Copy (right) */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-base font-bold text-primary">{mitigation.title}</span>
            {mitigation.confidence > 0 && <ConfidenceBar confidence={mitigation.confidence} />}
          </div>
          <CopyButton text={mitigation.action} />
        </div>
        <BulletText text={mitigation.action} className="text-sm text-secondary leading-relaxed mt-1.5" />
      </div>

      {/* Rationale */}
      {mitigation.rationale && (
        <div className="px-5 py-3 border-t border-default">
          <button
            onClick={() => setRationaleExpanded(!rationaleExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {rationaleExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-amber" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-amber" />}
            <Lightbulb className="w-3.5 h-3.5 text-accent-amber" />
            <span className="text-sm font-semibold text-accent-amber">Why this helps</span>
          </button>
          {rationaleExpanded && (
            <BulletText text={mitigation.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
          )}
        </div>
      )}

      {/* Addressed Friction Types */}
      {matchedTypes.length > 0 && (
        <div className="px-5 py-3 border-t border-default">
          <button
            onClick={() => setTypesExpanded(!typesExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {typesExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-amber" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-amber" />}
            <Target className="w-3.5 h-3.5 text-accent-amber" />
            <span className="text-sm font-semibold text-accent-amber">What this fixes</span>
            <span className="text-dimmed">({matchedTypes.length})</span>
          </button>
          {typesExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedTypes.map((ft) => (
                <div key={ft.type_name} className="border-l-2 border-accent-amber-border pl-3 space-y-1.5">
                  <h6 className="text-base font-semibold text-primary">
                    {frictionTypeLabel(ft.type_name)}
                  </h6>
                  <BulletText text={ft.description} className="text-sm text-secondary leading-relaxed" />
                  <FrictionRefList refs={ft.example_refs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
