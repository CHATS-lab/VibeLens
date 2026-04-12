import { BarChart3, Plus, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import type {
  SkillAnalysisResult,
  SkillMode,
  SkillSourceInfo,
} from "../../types";
import { TutorialBanner } from "../analysis-welcome";
import { DemoBanner } from "../demo-banner";
import { LoadingSpinnerRings } from "../loading-spinner";
import { Tooltip } from "../tooltip";
import { SHOW_ANALYSIS_DETAIL_SECTIONS } from "../../constants";
import { WarningsBanner } from "../warnings-banner";
import { CreationSection } from "./skill-creations-view";
import { EvolutionSection } from "./skill-evolutions-view";
import { PatternSection } from "./skill-patterns-view";
import { RecommendationSection } from "./skill-recommendations-view";

export type SkillTab = "local" | "explore" | "retrieve" | "create" | "evolve";

// Re-export SectionHeader so consumers that were importing from this file still work.
export { SectionHeader } from "./skill-shared";

const MODE_TITLES: Record<SkillMode, string> = {
  retrieval: "Skill Recommendation",
  creation: "Custom Skill Generation",
  evolution: "Installed Skill Evolution",
};

const MODE_ITEM_LABELS: Record<SkillMode, string> = {
  retrieval: "recommended skill",
  creation: "custom skill",
  evolution: "evolved skill",
};

const MODE_SUBLABELS: Record<SkillMode, string> = {
  retrieval: "Discovering skills that match your coding patterns",
  creation: "Generating custom skills from your workflow",
  evolution: "Checking installed skills against your usage",
};

export function AnalysisLoadingState({ mode, sessionCount }: { mode: SkillMode; sessionCount: number }) {
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
  tutorial,
}: {
  result: SkillAnalysisResult;
  activeTab: SkillTab;
  onNew: () => void;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  tutorial?: { title: string; description: string };
}) {
  const [agentSources, setAgentSources] = useState<SkillSourceInfo[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchWithToken("/api/skills/sources");
        if (res.ok) setAgentSources(await res.json());
      } catch {
        /* ignore */
      }
    })();
  }, [fetchWithToken]);

  return (
    <div className="max-w-4xl mx-auto px-6 py-6 space-y-8">
      {result.backend_id === "mock" && <DemoBanner />}
      {/* Header */}
      <ResultHeader result={result} onNew={onNew} mode={result.mode} />
      {tutorial && <TutorialBanner tutorial={tutorial} accentColor="teal" />}
      {result.warnings && result.warnings.length > 0 && (
        <WarningsBanner warnings={result.warnings} />
      )}

      {/* Recommended Skills (Recommend) */}
      {activeTab === "retrieve" && result.recommendations.length > 0 && (
        <RecommendationSection
          recommendations={result.recommendations}
          workflowPatterns={result.workflow_patterns}
          fetchWithToken={fetchWithToken}
          agentSources={agentSources}
        />
      )}

      {/* Generated Skills (Create) */}
      {activeTab === "create" && result.creations.length > 0 && (
        <CreationSection
          skills={result.creations}
          workflowPatterns={result.workflow_patterns}
          fetchWithToken={fetchWithToken}
          agentSources={agentSources}
        />
      )}

      {/* Evolution Suggestions (Evolve) */}
      {activeTab === "evolve" && result.evolutions.length > 0 && (
        <EvolutionSection
          suggestions={result.evolutions}
          workflowPatterns={result.workflow_patterns}
          fetchWithToken={fetchWithToken}
          agentSources={agentSources}
        />
      )}

      {/* Workflow Patterns — shown at the bottom */}
      {SHOW_ANALYSIS_DETAIL_SECTIONS && result.workflow_patterns.length > 0 && (
        <PatternSection patterns={result.workflow_patterns} />
      )}

      {/* Metadata footer */}
      <MetadataFooter result={result} />
    </div>
  );
}

function getItemCount(result: SkillAnalysisResult, mode: SkillMode): number {
  if (mode === "retrieval") return result.recommendations.length;
  if (mode === "creation") return result.creations.length;
  return result.evolutions.length;
}

function ResultHeader({
  result,
  onNew,
  mode,
}: {
  result: SkillAnalysisResult;
  onNew: () => void;
  mode: SkillMode;
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
            {(result.is_example || result.backend_id === "mock") && (
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

function MetadataFooter({ result }: { result: SkillAnalysisResult }) {
  const computedDate = new Date(result.created_at);
  const dateStr = isNaN(computedDate.getTime()) ? result.created_at : computedDate.toLocaleDateString();
  const timeStr = isNaN(computedDate.getTime()) ? "" : computedDate.toLocaleTimeString();

  return (
    <Tooltip text="Backend, model, and API cost">
      <div className="border-t border-default pt-4 text-xs text-dimmed flex items-center justify-between gap-4 w-full cursor-help">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{result.backend_id}/{result.model}</span>
          {result.metrics.cost_usd != null && (
            <span className="border-l border-card pl-2">
              ${result.metrics.cost_usd.toFixed(4)}
            </span>
          )}
          {result.duration_seconds != null && (
            <span className="inline-flex items-center gap-1 border-l border-card pl-2">
              <Timer className="w-3 h-3" />
              {formatDuration(result.duration_seconds)}
            </span>
          )}
        </div>
        <span className="shrink-0">{dateStr} {timeStr}</span>
      </div>
    </Tooltip>
  );
}
