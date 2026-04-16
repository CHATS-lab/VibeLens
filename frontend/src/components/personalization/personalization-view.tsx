import { BarChart3, Plus, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import type {
  PersonalizationResult,
  PersonalizationMode,
  SkillSyncTarget,
} from "../../types";
import { DemoBanner } from "../demo-banner";
import { LoadingSpinnerRings } from "../loading-spinner";
import { Tooltip } from "../tooltip";
import { SHOW_ANALYSIS_DETAIL_SECTIONS } from "../../constants";
import { WarningsBanner } from "../warnings-banner";
import { CreationSection } from "./creations-view";
import { EvolutionSection } from "./evolutions-view";
import { PatternSection } from "./patterns-view";
import { RecommendationSection } from "./recommendations-view";

export type PersonalizationTab = "local" | "explore" | "retrieve" | "create" | "evolve";

// Re-export SectionHeader so consumers that were importing from this file still work.
export { SectionHeader } from "./shared";

const MODE_TITLES: Record<PersonalizationMode, string> = {
  recommendation: "Skill Recommendation",
  creation: "Custom Skill Generation",
  evolution: "Installed Skill Evolution",
};

const MODE_ITEM_LABELS: Record<PersonalizationMode, string> = {
  recommendation: "recommended skill",
  creation: "custom skill",
  evolution: "evolved skill",
};

const MODE_SUBLABELS: Record<PersonalizationMode, string> = {
  recommendation: "Discovering skills that match your coding patterns",
  creation: "Generating custom skills from your workflow",
  evolution: "Checking installed skills against your usage",
};

export function AnalysisLoadingState({ mode, sessionCount }: { mode: PersonalizationMode; sessionCount: number }) {
  return (
    <div className="flex flex-col items-center gap-5">
      <LoadingSpinnerRings color="teal" />
      <div className="text-center space-y-1.5">
        <p className="text-base font-semibold text-primary">
          Analyzing {sessionCount} session{sessionCount !== 1 ? "s" : ""}
        </p>
        <p className="text-sm text-secondary">{MODE_SUBLABELS[mode]}</p>
      </div>
    </div>
  );
}

export function AnalysisResultView({
  result,
  activeTab,
  onNew,
  fetchWithToken,
}: {
  result: PersonalizationResult;
  activeTab: PersonalizationTab;
  onNew: () => void;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
}) {
  const [syncTargets, setSkillSyncTargets] = useState<SkillSyncTarget[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchWithToken("/api/skills?page_size=1");
        if (res.ok) {
          const data = await res.json();
          setSkillSyncTargets(data.sync_targets ?? []);
        }
      } catch {
        /* ignore */
      }
    })();
  }, [fetchWithToken]);

  return (
    <div className="max-w-4xl mx-auto px-6 py-6 space-y-8">
      {result.backend === "mock" && <DemoBanner />}
      {/* Header */}
      <ResultHeader result={result} onNew={onNew} mode={result.mode} />
      {result.warnings && result.warnings.length > 0 && (
        <WarningsBanner warnings={result.warnings} />
      )}

      {/* Recommended Skills (Recommend) */}
      {activeTab === "retrieve" && result.recommendations.length > 0 && (
        <RecommendationSection
          recommendations={result.recommendations}
          fetchWithToken={fetchWithToken}
          syncTargets={syncTargets}
        />
      )}

      {/* Generated Skills (Create) */}
      {activeTab === "create" && result.creations.length > 0 && (
        <CreationSection
          skills={result.creations}
          workflowPatterns={result.workflow_patterns}
          fetchWithToken={fetchWithToken}
          syncTargets={syncTargets}
        />
      )}

      {/* Evolution Suggestions (Evolve) */}
      {activeTab === "evolve" && result.evolutions.length > 0 && (
        <EvolutionSection
          suggestions={result.evolutions}
          workflowPatterns={result.workflow_patterns}
          fetchWithToken={fetchWithToken}
          syncTargets={syncTargets}
        />
      )}

      {/* Workflow Patterns — shown at the bottom (hidden for retrieve) */}
      {SHOW_ANALYSIS_DETAIL_SECTIONS && activeTab !== "retrieve" && result.workflow_patterns.length > 0 && (
        <PatternSection patterns={result.workflow_patterns} />
      )}

      {/* Metadata footer */}
      <MetadataFooter result={result} />
    </div>
  );
}

function getItemCount(result: PersonalizationResult, mode: PersonalizationMode): number {
  if (mode === "recommendation") return result.recommendations.length;
  if (mode === "creation") return result.creations.length;
  return result.evolutions.length;
}

function ResultHeader({
  result,
  onNew,
  mode,
}: {
  result: PersonalizationResult;
  onNew: () => void;
  mode: PersonalizationMode;
}) {
  const itemCount = getItemCount(result, mode);
  const itemLabel = MODE_ITEM_LABELS[mode];
  const sessionCount = result.session_ids.length;

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <BarChart3 className="w-6 h-6 text-accent-teal" />
        <div>
          <div className="flex items-center gap-2.5">
            {(result.is_example || result.backend === "mock") && (
              <span className="px-2 py-0.5 rounded border text-[11px] font-semibold bg-accent-amber-subtle border-accent-amber text-accent-amber">
                Example
              </span>
            )}
            <h2 className="text-xl font-bold text-primary">
              {result.title || MODE_TITLES[mode]}
            </h2>
          </div>
          <p className="text-sm text-muted">
            {itemCount} {itemLabel}{itemCount !== 1 ? "s" : ""} across {sessionCount} session{sessionCount !== 1 ? "s" : ""}
            {result.skipped_session_ids.length > 0 && (
              <span className="text-dimmed">
                {" "}&middot; {result.skipped_session_ids.length} skipped
              </span>
            )}
          </p>
        </div>
      </div>
      <Tooltip text="Analyze your own sessions">
        <button
          onClick={onNew}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-teal hover:text-teal-800 dark:hover:text-white bg-accent-teal-subtle hover:bg-teal-100 dark:hover:bg-teal-600/40 border border-accent-teal rounded-lg transition"
        >
          <Plus className="w-3.5 h-3.5" /> New
        </button>
      </Tooltip>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function MetadataFooter({ result }: { result: PersonalizationResult }) {
  const computedDate = new Date(result.created_at);
  const dateStr = isNaN(computedDate.getTime()) ? result.created_at : computedDate.toLocaleDateString();
  const timeStr = isNaN(computedDate.getTime()) ? "" : computedDate.toLocaleTimeString();

  return (
    <Tooltip text="Backend, model, and API cost">
      <div className="border-t border-default pt-4 text-xs text-dimmed flex items-center justify-between gap-4 w-full cursor-help">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{result.backend}/{result.model}</span>
          {result.final_metrics?.total_cost_usd != null && (
            <span className="border-l border-card pl-2">
              ${result.final_metrics.total_cost_usd.toFixed(4)}
            </span>
          )}
          {result.final_metrics?.duration != null && result.final_metrics.duration > 0 && (
            <span className="inline-flex items-center gap-1 border-l border-card pl-2">
              <Timer className="w-3 h-3" />
              {formatDuration(result.final_metrics.duration)}
            </span>
          )}
        </div>
        <span className="shrink-0">{dateStr} {timeStr}</span>
      </div>
    </Tooltip>
  );
}
