import { ArrowRight, BarChart3, Plus, Search, Sparkles, Timer, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type {
  ExtensionItemSummary,
  ExtensionSyncTarget,
  PersonalizationResult,
  PersonalizationMode,
  SkillSyncTarget,
} from "../../types";
import { useExtensionsClient } from "../../app";
import { DemoBanner } from "../demo-banner";
import { Tooltip } from "../ui/tooltip";
import { SHOW_ANALYSIS_DETAIL_SECTIONS } from "../../constants";
import { WarningsBanner } from "../warnings-banner";
import { CreationSection } from "./creations-view";
import { EvolutionSection } from "./evolutions-view";
import { ExtensionDetailView } from "./extensions/extension-detail-view";
import { PatternSection } from "./patterns-view";
import { RecommendationSection } from "./recommendations-view";

export type PersonalizationTab =
  | "local"
  | "collections"
  | "explore"
  | "retrieve"
  | "create"
  | "evolve";

// Re-export SectionHeader so consumers that were importing from this file still work.
export { SectionHeader } from "./result-shared";

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

export function AnalysisResultView({
  result,
  activeTab,
  onNew,
  onInstalled,
  onSwitchTab,
  detailItem,
  onDetailChange,
}: {
  result: PersonalizationResult;
  activeTab: PersonalizationTab;
  onNew: () => void;
  onInstalled?: () => void;
  onSwitchTab?: (tab: PersonalizationTab) => void;
  detailItem: ExtensionItemSummary | null;
  onDetailChange: (item: ExtensionItemSummary | null) => void;
}) {
  const client = useExtensionsClient();
  const [syncTargets, setSkillSyncTargets] = useState<SkillSyncTarget[]>([]);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [syncTargetsByType, setSyncTargetsByType] = useState<Record<string, ExtensionSyncTarget[]>>({});

  useEffect(() => {
    client.skills.list({ pageSize: 1 })
      .then((data) => {
        const targets: SkillSyncTarget[] = data.sync_targets.map((t) => ({
          agent: t.agent,
          skill_count: t.count,
          skills_dir: t.dir,
        }));
        setSkillSyncTargets(targets);
      })
      .catch(() => {});

    client.syncTargets.get()
      .then((targets) => setSyncTargetsByType(targets))
      .catch(() => {});
  }, [client]);

  const handleInstalled = useCallback(
    (itemId: string) => {
      setInstalledIds((prev) => new Set([...prev, itemId]));
      onInstalled?.();
    },
    [onInstalled],
  );

  // When a detail item is selected, render ExtensionDetailView at top level
  // (outside the max-w-4xl wrapper) to match the explore tab layout.
  if (detailItem) {
    return (
      <ExtensionDetailView
        item={detailItem}
        isInstalled={installedIds.has(detailItem.extension_id)}
        onBack={() => onDetailChange(null)}
        onInstalled={handleInstalled}
        syncTargets={syncTargetsByType[detailItem.extension_type] ?? []}
      />
    );
  }

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
          installedIds={installedIds}
          onOpenDetail={onDetailChange}
          syncTargetsByType={syncTargetsByType}
          onInstalled={handleInstalled}
        />
      )}

      {/* Generated Skills (Create) */}
      {activeTab === "create" && result.creations.length > 0 && (
        <CreationSection
          skills={result.creations}
          workflowPatterns={result.workflow_patterns}
          syncTargets={syncTargets}
          onInstalled={onInstalled}
        />
      )}

      {/* Evolution Suggestions (Evolve) */}
      {activeTab === "evolve" && result.evolutions.length > 0 && (
        <EvolutionSection
          suggestions={result.evolutions}
          workflowPatterns={result.workflow_patterns}
          syncTargets={syncTargets}
          onInstalled={onInstalled}
        />
      )}

      {/* Empty-state for Evolve with zero surviving proposals */}
      {activeTab === "evolve" && result.evolutions.length === 0 && (
        <EvolveEmptyState onSwitchTab={onSwitchTab} />
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

function EvolveEmptyState({
  onSwitchTab,
}: {
  onSwitchTab?: (tab: PersonalizationTab) => void;
}) {
  return (
    <div className="relative w-full rounded-lg border border-teal-300 dark:border-tutorial-teal-border bg-teal-50 dark:bg-tutorial-teal-bg px-6 py-8 overflow-hidden">
      <div className="flex flex-col items-center text-center gap-3 mb-6">
        <div className="shrink-0 p-3 rounded-xl bg-teal-100 dark:bg-teal-500/15 border border-teal-200 dark:border-teal-500/20">
          <TrendingUp className="w-6 h-6 text-teal-600 dark:text-teal-400" />
        </div>
        <div className="space-y-1.5 max-w-md">
          <h3 className="text-base font-semibold text-primary">
            No skill evolutions to suggest
          </h3>
          <p className="text-sm text-secondary leading-relaxed">
            Your installed skills do not match your recent work. Try finding skills that fit your workflow, or generate a new one from scratch.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl mx-auto">
        <EmptyStateAction
          icon={Search}
          label="Recommend skills"
          description="Search the catalog for skills that match your sessions."
          accent="teal"
          onClick={() => onSwitchTab?.("retrieve")}
          disabled={!onSwitchTab}
        />
        <EmptyStateAction
          icon={Sparkles}
          label="Generate a skill"
          description="Create a custom SKILL.md from patterns we detected."
          accent="emerald"
          onClick={() => onSwitchTab?.("create")}
          disabled={!onSwitchTab}
        />
      </div>
    </div>
  );
}

function EmptyStateAction({
  icon: Icon,
  label,
  description,
  accent,
  onClick,
  disabled,
}: {
  icon: LucideIcon;
  label: string;
  description: string;
  accent: "teal" | "emerald";
  onClick: () => void;
  disabled?: boolean;
}) {
  const styles = {
    teal: {
      container: "border-teal-200 dark:border-teal-500/20 bg-panel hover:border-teal-400 dark:hover:border-teal-400/40 hover:bg-teal-50/80 dark:hover:bg-teal-500/10",
      iconBg: "bg-teal-100 dark:bg-teal-500/15 border border-teal-200 dark:border-teal-500/20",
      icon: "text-teal-600 dark:text-teal-400",
      arrow: "text-teal-600 dark:text-teal-400",
    },
    emerald: {
      container: "border-emerald-200 dark:border-emerald-500/20 bg-panel hover:border-emerald-400 dark:hover:border-emerald-400/40 hover:bg-emerald-50/80 dark:hover:bg-emerald-500/10",
      iconBg: "bg-emerald-100 dark:bg-emerald-500/15 border border-emerald-200 dark:border-emerald-500/20",
      icon: "text-emerald-600 dark:text-emerald-400",
      arrow: "text-emerald-600 dark:text-emerald-400",
    },
  }[accent];

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`group flex items-start gap-3 px-4 py-3 text-left rounded-lg border transition disabled:opacity-40 disabled:cursor-not-allowed ${styles.container}`}
    >
      <div className={`shrink-0 p-2 rounded-lg ${styles.iconBg}`}>
        <Icon className={`w-4 h-4 ${styles.icon}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-semibold text-primary">{label}</span>
          <ArrowRight className={`w-3.5 h-3.5 ${styles.arrow} opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition`} />
        </div>
        <p className="text-xs text-secondary mt-0.5 leading-relaxed">{description}</p>
      </div>
    </button>
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
