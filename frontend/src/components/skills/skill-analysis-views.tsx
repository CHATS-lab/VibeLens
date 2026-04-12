import {
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Eye,

  Lightbulb,
  Loader2,
  Pencil,
  Plus,
  Repeat,
  Search,
  Sparkles,
  Target,
  Timer,
  TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type {
  SkillAnalysisResult,
  SkillCreation,
  SkillEvolution,
  SkillMode,
  SkillRecommendation,
  SkillSourceInfo,
  StepRef,
  WorkflowPattern,
} from "../../types";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import { BulletText } from "../bullet-text";
import { TutorialBanner } from "../analysis-welcome";
import { DemoBanner } from "../demo-banner";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { LoadingSpinnerRings } from "../loading-spinner";
import { Tooltip } from "../tooltip";
import { SHOW_ANALYSIS_DETAIL_SECTIONS } from "../../constants";
import { WarningsBanner } from "../warnings-banner";
import { applySkillEdits } from "./skill-edit-utils";
import { EvolutionDiffView } from "./skill-evolution-diff";
import { SkillPreviewDialog } from "./skill-preview-dialog";

export type SkillTab = "local" | "explore" | "retrieve" | "create" | "evolve";

const CONFIDENCE_THRESHOLDS = { HIGH: 0.75, MEDIUM: 0.5 } as const;

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

function SectionHeader({
  icon,
  title,
  tooltip,
  accentColor = "text-accent-teal",
}: {
  icon: React.ReactNode;
  title: string;
  tooltip: string;
  accentColor?: string;
}) {
  return (
    <Tooltip text={tooltip}>
      <div className="flex items-center gap-2 mb-3 cursor-help">
        <span className={accentColor}>{icon}</span>
        <h3 className="text-lg font-semibold text-primary">{title}</h3>
      </div>
    </Tooltip>
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

/* ── Workflow Patterns ── */

function PatternSection({ patterns }: { patterns: WorkflowPattern[] }) {
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

function StepRefList({ refs }: { refs: StepRef[] }) {
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

/* ── Recommendations (Recommend) ── */

function RecommendationSection({
  recommendations,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  recommendations: SkillRecommendation[];
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  return (
    <section>
      <SectionHeader
        icon={<Search className="w-5 h-5" />}
        title="Recommended Skills"
        tooltip="Catalog skills matching your workflow"
      />
      <div className="space-y-3">
        {recommendations.map((rec) => (
          <RecommendationCard
            key={rec.skill_name}
            rec={rec}
            workflowPatterns={workflowPatterns}
            fetchWithToken={fetchWithToken}
            agentSources={agentSources}
          />
        ))}
      </div>
    </section>
  );
}

function RecommendationCard({
  rec,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  rec: SkillRecommendation;
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [rationaleExpanded, setRationaleExpanded] = useState(true);
  const [patternsExpanded, setPatternsExpanded] = useState(false);

  const matchedPatterns = workflowPatterns.filter((p) =>
    rec.addressed_patterns.includes(p.title),
  );

  const handlePreview = useCallback(async () => {
    setShowPreview(true);
    if (previewContent !== null) return;
    setLoadingPreview(true);
    try {
      const res = await fetchWithToken(`/api/skills/featured/${rec.skill_name}/content`);
      if (res.ok) {
        const data = await res.json();
        setPreviewContent(data.content);
      } else {
        setPreviewContent("(Content unavailable)");
      }
    } catch {
      setPreviewContent("(Failed to fetch content)");
    } finally {
      setLoadingPreview(false);
    }
  }, [fetchWithToken, rec.skill_name, previewContent]);

  const handleInstall = useCallback(async (_content: string, targets: string[]) => {
    try {
      const res = await fetchWithToken("/api/skills/featured/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: rec.skill_name, targets }),
      });
      if (res.ok) setInstalled(true);
    } catch {
      /* ignore */
    }
    setShowPreview(false);
  }, [fetchWithToken, rec.skill_name]);

  return (
    <div className="border border-zinc-200 dark:border-zinc-700/30 rounded-xl bg-zinc-50/50 dark:bg-zinc-800/20 overflow-hidden">
      {/* Header: Name + Confidence + Action */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-base font-bold text-primary">{rec.skill_name}</span>
            {rec.confidence > 0 && <ConfidenceBar confidence={rec.confidence} accentColor="teal" />}
          </div>
          <div className="flex items-center gap-2.5">
            {installed ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-teal bg-accent-teal-subtle rounded-lg border border-accent-teal">
                <Check className="w-3.5 h-3.5" /> Installed
              </span>
            ) : (
              <Tooltip text="Preview and install skill">
                <button
                  onClick={() => guardAction(handlePreview)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition"
                >
                  <Eye className="w-3.5 h-3.5" />
                  Preview &amp; Install
                </button>
              </Tooltip>
            )}
          </div>
        </div>
        {rec.description && (
          <p className="text-sm text-secondary leading-relaxed mt-1.5">
            <span className="font-semibold text-secondary">Skill Description: </span>
            {rec.description}
          </p>
        )}
      </div>

      {/* Why this helps */}
      <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
        <button
          onClick={() => setRationaleExpanded(!rationaleExpanded)}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {rationaleExpanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
          <Lightbulb className="w-3.5 h-3.5 text-accent-teal" />
          <span className="text-sm font-semibold text-accent-teal uppercase tracking-wide">Why this helps</span>
        </button>
        {rationaleExpanded && (
          <BulletText text={rec.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>

      {/* Toggleable What this covers */}
      {matchedPatterns.length > 0 && (
        <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
          <button
            onClick={() => setPatternsExpanded(!patternsExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {patternsExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
            <Target className="w-3.5 h-3.5 text-accent-teal" />
            <span className="text-sm font-semibold text-accent-teal uppercase tracking-wide">What this covers</span>
            <span className="text-dimmed">({matchedPatterns.length})</span>
          </button>
          {patternsExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedPatterns.map((p, i) => (
                <div key={i} className="border-l-2 border-teal-300 dark:border-teal-700/50 pl-3 space-y-1.5">
                  <h6 className="text-sm font-semibold text-primary">{p.title}</h6>
                  <BulletText text={p.description} className="text-sm text-secondary leading-relaxed" />
                  <StepRefList refs={p.example_refs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {showPreview && (
        <SkillPreviewDialog
          skillName={rec.skill_name}
          content={previewContent ?? ""}
          onInstall={handleInstall}
          onCancel={() => setShowPreview(false)}
          agentSources={agentSources}
          loading={loadingPreview}
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

/* ── Generated Skills (Create) ── */

function CreationSection({
  skills,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  skills: SkillCreation[];
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  return (
    <section>
      <SectionHeader
        icon={<Sparkles className="w-5 h-5" />}
        title="Custom Skills"
        tooltip="Generated skills from your patterns"
        accentColor="text-accent-emerald"
      />
      <div className="space-y-3">
        {skills.map((skill) => (
          <CreatedSkillCard
            key={skill.name}
            skill={skill}
            workflowPatterns={workflowPatterns}
            fetchWithToken={fetchWithToken}
            agentSources={agentSources}
          />
        ))}
      </div>
    </section>
  );
}

function ConfidenceBar({ confidence, accentColor = "emerald" }: { confidence: number; accentColor?: "emerald" | "amber" | "teal" }) {
  const pct = Math.round(confidence * 100);
  const isHigh = confidence >= CONFIDENCE_THRESHOLDS.HIGH;
  const isMedium = confidence >= CONFIDENCE_THRESHOLDS.MEDIUM;

  const HIGH_COLORS: Record<string, { bar: string; text: string }> = {
    emerald: { bar: "bg-emerald-500", text: "text-accent-emerald" },
    amber: { bar: "bg-amber-500", text: "text-amber-700 dark:text-amber-400" },
    teal: { bar: "bg-teal-500", text: "text-accent-teal" },
  };
  const high = HIGH_COLORS[accentColor];
  const barColor = isHigh ? high.bar : isMedium ? "bg-amber-500" : "bg-zinc-600";
  const textColor = isHigh ? high.text : isMedium ? "text-amber-700 dark:text-amber-400" : "text-dimmed";

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

function CreatedSkillCard({
  skill,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  skill: SkillCreation;
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [showPreview, setShowPreview] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [editedContent, setEditedContent] = useState(skill.skill_md_content);
  const [rationaleExpanded, setRationaleExpanded] = useState(true);
  const [patternsExpanded, setPatternsExpanded] = useState(false);

  const matchedPatterns = workflowPatterns.filter((p) =>
    skill.addressed_patterns?.includes(p.title),
  );

  const handleInstall = useCallback(
    async (content: string, targets: string[]) => {
      try {
        const res = await fetchWithToken("/api/skills/install", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: skill.name, content }),
        });
        if (!res.ok) return;

        if (targets.length > 0) {
          await fetchWithToken(`/api/skills/sync/${skill.name}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ targets }),
          });
        }
        setInstalled(true);
      } catch {
        /* ignore */
      }
      setShowPreview(false);
    },
    [fetchWithToken, skill.name],
  );

  return (
    <div className="border border-zinc-200 dark:border-zinc-700/30 rounded-xl bg-zinc-50/50 dark:bg-zinc-800/20 overflow-hidden">
      {/* Header: Name + Confidence + Action */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-sm font-bold text-primary">{skill.name}</span>
            {skill.confidence > 0 && <ConfidenceBar confidence={skill.confidence} />}
          </div>
          <div className="flex items-center gap-2">
            {installed ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-emerald bg-accent-emerald-subtle rounded-lg border border-accent-emerald">
                <Check className="w-3.5 h-3.5" /> Installed
              </span>
            ) : (
              <Tooltip text="Preview and install skill">
                <button
                  onClick={() => guardAction(() => setShowPreview(true))}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg transition"
                >
                  <Eye className="w-3.5 h-3.5" />
                  Preview &amp; Install
                </button>
              </Tooltip>
            )}
          </div>
        </div>
        <p className="text-sm text-secondary leading-relaxed mt-1.5">
          <span className="font-semibold text-secondary">Skill Description: </span>
          {skill.description}
        </p>
      </div>

      {/* Why this helps */}
      <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
        <button
          onClick={() => setRationaleExpanded(!rationaleExpanded)}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {rationaleExpanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-emerald" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-emerald" />}
          <Lightbulb className="w-3.5 h-3.5 text-accent-emerald" />
          <span className="text-sm font-semibold text-accent-emerald uppercase tracking-wide">Why this helps</span>
        </button>
        {rationaleExpanded && (
          <BulletText text={skill.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>

      {/* Toggleable What this covers */}
      {matchedPatterns.length > 0 && (
        <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
          <button
            onClick={() => setPatternsExpanded(!patternsExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {patternsExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-emerald" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-emerald" />}
            <Target className="w-3.5 h-3.5 text-accent-emerald" />
            <span className="text-sm font-semibold text-accent-emerald uppercase tracking-wide">What this covers</span>
            <span className="text-dimmed">({matchedPatterns.length})</span>
          </button>
          {patternsExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedPatterns.map((p, i) => (
                <div key={i} className="border-l-2 border-emerald-300 dark:border-emerald-700/50 pl-3 space-y-1.5">
                  <h6 className="text-sm font-semibold text-primary">{p.title}</h6>
                  <BulletText text={p.description} className="text-sm text-secondary leading-relaxed" />
                  <StepRefList refs={p.example_refs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {showPreview && (
        <SkillPreviewDialog
          skillName={skill.name}
          content={editedContent}
          onContentChange={setEditedContent}
          onInstall={handleInstall}
          onCancel={() => setShowPreview(false)}
          agentSources={agentSources}
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

/* ── Evolution Suggestions (Evolve) ── */

function EvolutionSection({
  suggestions,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  suggestions: SkillEvolution[];
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  return (
    <section>
      <SectionHeader
        icon={<TrendingUp className="w-5 h-5" />}
        title="Evolution Suggestions"
        tooltip="Targeted improvements for your installed skills based on real usage"
        accentColor="text-accent-teal"
      />
      <div className="space-y-3">
        {suggestions.map((sug) => (
          <EvolutionCard
            key={sug.skill_name}
            suggestion={sug}
            workflowPatterns={workflowPatterns}
            fetchWithToken={fetchWithToken}
            agentSources={agentSources}
          />
        ))}
      </div>
    </section>
  );
}

function EvolutionCard({
  suggestion,
  workflowPatterns,
  fetchWithToken,
  agentSources,
}: {
  suggestion: SkillEvolution;
  workflowPatterns: WorkflowPattern[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [expanded, setExpanded] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [rationaleExpanded, setRationaleExpanded] = useState(true);
  const [patternsExpanded, setPatternsExpanded] = useState(false);

  const matchedPatterns = workflowPatterns.filter((p) =>
    suggestion.addressed_patterns?.includes(p.title),
  );
  const [originalContent, setOriginalContent] = useState<string | null>(null);
  const [mergedContent, setMergedContent] = useState<string | null>(null);
  const [loadingOriginal, setLoadingOriginal] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [updated, setUpdated] = useState(false);

  const fetchOriginal = useCallback(async (): Promise<string | null> => {
    if (originalContent !== null) return originalContent;
    setLoadingOriginal(true);
    setFetchError(null);
    try {
      const res = await fetchWithToken(`/api/skills/local/${suggestion.skill_name}`);
      if (res.status === 404) {
        setFetchError("Skill not found in central store");
        return null;
      }
      if (!res.ok) {
        setFetchError("Failed to fetch skill content");
        return null;
      }
      const data = await res.json();
      setOriginalContent(data.content);
      return data.content as string;
    } catch {
      setFetchError("Network error fetching skill");
      return null;
    } finally {
      setLoadingOriginal(false);
    }
  }, [fetchWithToken, suggestion.skill_name, originalContent]);

  const handleExpand = useCallback(async () => {
    const willExpand = !expanded;
    setExpanded(willExpand);
    if (willExpand && originalContent === null) {
      await fetchOriginal();
    }
  }, [expanded, originalContent, fetchOriginal]);

  const handlePreview = useCallback(async () => {
    const content = await fetchOriginal();
    if (!content) return;
    const merged = applySkillEdits(content, suggestion.edits);
    setMergedContent(merged);
    setShowPreview(true);
  }, [fetchOriginal, suggestion.edits]);

  const handleUpdate = useCallback(async (content: string, targets: string[]) => {
    try {
      const res = await fetchWithToken(`/api/skills/local/${suggestion.skill_name}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: suggestion.skill_name, content }),
      });
      if (!res.ok) return;

      if (targets.length > 0) {
        await fetchWithToken(`/api/skills/sync/${suggestion.skill_name}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ targets }),
        });
      }
      setUpdated(true);
    } catch {
      /* ignore */
    }
    setShowPreview(false);
  }, [fetchWithToken, suggestion.skill_name]);

  return (
    <div className="border border-zinc-200 dark:border-zinc-700/30 rounded-xl bg-zinc-50/50 dark:bg-zinc-800/20 overflow-hidden">
      {/* Header: Name + Badges + Confidence + Action */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-base font-bold text-primary">{suggestion.skill_name}</span>
            <Tooltip text={`${suggestion.edits.length} edit${suggestion.edits.length !== 1 ? "s" : ""} suggested`}>
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-accent-teal-subtle text-accent-teal border border-accent-teal cursor-help">
                <Pencil className="w-2.5 h-2.5" />
                {suggestion.edits.length} edit{suggestion.edits.length !== 1 ? "s" : ""}
              </span>
            </Tooltip>
            {suggestion.confidence > 0 && <ConfidenceBar confidence={suggestion.confidence} accentColor="teal" />}
          </div>
          <div className="flex items-center gap-2.5">
            {updated ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-teal bg-accent-teal-subtle rounded-lg border border-accent-teal">
                <Check className="w-3.5 h-3.5" /> Updated
              </span>
            ) : (
              <Tooltip text="Preview merged result">
                <button
                  onClick={() => guardAction(handlePreview)}
                  disabled={loadingOriginal}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition disabled:opacity-50"
                >
                  {loadingOriginal
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Eye className="w-3.5 h-3.5" />}
                  Preview &amp; Update
                </button>
              </Tooltip>
            )}
            {fetchError && <span className="text-xs text-red-600 dark:text-red-400">{fetchError}</span>}
          </div>
        </div>
        {suggestion.description && (
          <p className="text-sm text-secondary leading-relaxed mt-1.5">
            <span className="font-semibold text-secondary">Skill Description: </span>
            {suggestion.description}
          </p>
        )}
      </div>

      {/* Why this helps */}
      <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
        <button
          onClick={() => setRationaleExpanded(!rationaleExpanded)}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {rationaleExpanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
          <Lightbulb className="w-3.5 h-3.5 text-accent-teal" />
          <span className="text-sm font-semibold text-accent-teal uppercase tracking-wide">Why this helps</span>
        </button>
        {rationaleExpanded && (
          <BulletText text={suggestion.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>

      {/* Toggleable What this covers */}
      {matchedPatterns.length > 0 && (
        <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
          <button
            onClick={() => setPatternsExpanded(!patternsExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {patternsExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
            <Target className="w-3.5 h-3.5 text-accent-teal" />
            <span className="text-sm font-semibold text-accent-teal uppercase tracking-wide">What this covers</span>
            <span className="text-dimmed">({matchedPatterns.length})</span>
          </button>
          {patternsExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedPatterns.map((p, i) => (
                <div key={i} className="border-l-2 border-teal-300 dark:border-teal-700/50 pl-3 space-y-1.5">
                  <h6 className="text-sm font-semibold text-primary">{p.title}</h6>
                  <BulletText text={p.description} className="text-sm text-secondary leading-relaxed" />
                  <StepRefList refs={p.example_refs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Toggleable Proposed Edits */}
      <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
        <button
          onClick={handleExpand}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {expanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
          <Pencil className="w-3.5 h-3.5 text-accent-teal" />
          <span className="text-sm font-semibold text-accent-teal uppercase tracking-wide">Proposed Edits</span>
          <span className="text-dimmed">({suggestion.edits.length})</span>
        </button>
        {expanded && suggestion.edits.length > 0 && (
          <div className="mt-2.5">
            <EvolutionDiffView
              skillName={suggestion.skill_name}
              edits={suggestion.edits}
              originalContent={originalContent ?? undefined}
            />
          </div>
        )}
      </div>
      {showPreview && mergedContent !== null && (
        <SkillPreviewDialog
          skillName={suggestion.skill_name}
          content={mergedContent}
          onContentChange={setMergedContent}
          onInstall={handleUpdate}
          onCancel={() => setShowPreview(false)}
          agentSources={agentSources}
          variant="update"
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

