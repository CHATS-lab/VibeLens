import {
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  FileCode,
  GitBranch,
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
  User,
  Zap,
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
import { DemoBanner } from "../demo-banner";
import { Tooltip } from "../tooltip";
import { WarningsBanner } from "../warnings-banner";
import { applySkillEdits } from "./skill-edit-utils";
import { EvolutionDiffView } from "./skill-evolution-diff";
import { SkillPreviewDialog } from "./skill-preview-dialog";

export type SkillTab = "local" | "explore" | "retrieve" | "create" | "evolve";

const CONFIDENCE_THRESHOLDS = { HIGH: 0.75, MEDIUM: 0.5 } as const;

const MODE_TITLES: Record<SkillMode, string> = {
  retrieval: "Skill Recommendation Analysis",
  creation: "Custom Skill Generation",
  evolution: "Installed Skill Evolution",
};

const MODE_SUBLABELS: Record<SkillMode, string> = {
  retrieval: "Discovering skills that match your coding patterns",
  creation: "Generating custom skills from your workflow",
  evolution: "Checking installed skills against your usage",
};

export function AnalysisLoadingState({ mode, sessionCount }: { mode: SkillMode; sessionCount: number }) {
  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative">
        <div className="absolute inset-0 rounded-full bg-teal-500/20 animate-ping" />
        <Loader2 className="w-12 h-12 text-teal-400 animate-spin relative" />
      </div>
      <div className="text-center">
        <p className="text-base font-semibold text-zinc-100">
          Analyzing {sessionCount} session{sessionCount !== 1 ? "s" : ""}
        </p>
        <p className="text-sm text-zinc-300 mt-1.5">{MODE_SUBLABELS[mode]}</p>
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
  result: SkillAnalysisResult;
  activeTab: SkillTab;
  onNew: () => void;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
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
      {result.warnings && result.warnings.length > 0 && (
        <WarningsBanner warnings={result.warnings} />
      )}

      {/* Summary card */}
      <SummaryCard summary={result.summary} userProfile={result.user_profile} />

      {/* Recommended Skills (Recommend) */}
      {activeTab === "retrieve" && result.recommendations.length > 0 && (
        <RecommendationSection
          recommendations={result.recommendations}
          fetchWithToken={fetchWithToken}
          agentSources={agentSources}
        />
      )}

      {/* Generated Skills (Create) */}
      {activeTab === "create" && result.creations.length > 0 && (
        <CreationSection
          skills={result.creations}
          fetchWithToken={fetchWithToken}
          agentSources={agentSources}
        />
      )}

      {/* Evolution Suggestions (Evolve) */}
      {activeTab === "evolve" && result.evolutions.length > 0 && (
        <EvolutionSection
          suggestions={result.evolutions}
          fetchWithToken={fetchWithToken}
          agentSources={agentSources}
        />
      )}

      {/* Workflow Patterns — shown at the bottom */}
      {result.workflow_patterns.length > 0 && (
        <PatternSection patterns={result.workflow_patterns} />
      )}

      {/* Metadata footer */}
      <MetadataFooter result={result} />
    </div>
  );
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
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-zinc-100">{result.title || MODE_TITLES[mode]}</h1>
        <button
          onClick={onNew}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
        >
          <Plus className="w-3 h-3" /> New
        </button>
      </div>
      <div className="flex items-center gap-3">
        <BarChart3 className="w-6 h-6 text-teal-400" />
        <div>
          <h2 className="text-base font-semibold text-zinc-200">
            {result.workflow_patterns.length} pattern{result.workflow_patterns.length !== 1 ? "s" : ""} detected
          </h2>
          <p className="text-sm text-zinc-400">
            {result.session_ids.length} session{result.session_ids.length !== 1 ? "s" : ""} analyzed
            {result.skipped_session_ids.length > 0 && (
              <span className="text-zinc-500">
                {" "}&middot; {result.skipped_session_ids.length} skipped
              </span>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ summary, userProfile }: { summary: string; userProfile: string }) {
  return (
    <div className="space-y-4">
      <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-5">
        <p className="text-sm text-zinc-200 leading-relaxed">{summary}</p>
      </div>
      {userProfile && (
        <div className="bg-gradient-to-r from-violet-950/30 to-zinc-900/60 border border-violet-700/30 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-2.5">
            <div className="p-1.5 rounded-lg bg-violet-600/15">
              <User className="w-4 h-4 text-violet-400" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-100">User Profile</h3>
          </div>
          <p className="text-sm text-zinc-300 leading-relaxed pl-[2.375rem]">{userProfile}</p>
        </div>
      )}
    </div>
  );
}

function SectionHeader({
  icon,
  title,
  tooltip,
  accentColor = "text-teal-400",
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
        <h3 className="text-base font-semibold text-zinc-100">{title}</h3>
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
      <div className="border-t border-zinc-800 pt-4 text-xs text-zinc-500 flex items-center justify-between gap-4 w-full cursor-help">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{result.backend_id}/{result.model}</span>
          {result.metrics.cost_usd != null && (
            <span className="border-l border-zinc-700 pl-2">
              ${result.metrics.cost_usd.toFixed(4)}
            </span>
          )}
          {result.duration_seconds != null && (
            <span className="inline-flex items-center gap-1 border-l border-zinc-700 pl-2">
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
        title="Workflow Patterns"
        tooltip="Recurring patterns detected across sessions"
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
    <div className="group border border-zinc-700/50 rounded-xl bg-zinc-800/40 hover:border-zinc-600/60 transition-all">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-5 py-4 flex items-start gap-3"
      >
        <div className="shrink-0 mt-0.5 p-1.5 rounded-lg bg-teal-600/15 group-hover:bg-teal-600/25 transition">
          <GitBranch className="w-4 h-4 text-teal-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5">
            <h5 className="text-sm font-bold text-zinc-100">{pattern.title}</h5>
            <Tooltip text={`Seen ${pattern.frequency}x across sessions`}>
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-teal-900/30 text-teal-300 border border-teal-700/20">
                <Repeat className="w-2.5 h-2.5" />
                {pattern.frequency}x
              </span>
            </Tooltip>
          </div>
          <p className="text-sm text-zinc-300 leading-relaxed mt-1">{pattern.description}</p>
        </div>
        <div className="shrink-0 mt-1">
          {expanded
            ? <ChevronDown className="w-4 h-4 text-zinc-500" />
            : <ChevronRight className="w-4 h-4 text-zinc-500" />}
        </div>
      </button>
      {expanded && (
        <div className="px-5 pb-4 pl-[3.25rem] space-y-4 border-t border-zinc-700/30 pt-4 mx-3 mb-1">
          {/* Gap */}
          <div className="rounded-lg bg-amber-950/15 border border-amber-800/20 px-4 py-3">
            <Tooltip text="Automation gap in this workflow">
              <div className="flex items-center gap-1.5 text-xs text-amber-400/80 mb-1.5 cursor-help">
                <Zap className="w-3.5 h-3.5" />
                <span className="font-semibold uppercase tracking-wider">Gap</span>
              </div>
            </Tooltip>
            <p className="text-sm text-amber-200/80 leading-relaxed">{pattern.gap}</p>
          </div>

          {/* Example Steps */}
          <StepRefList refs={pattern.example_refs} />
        </div>
      )}
    </div>
  );
}

function StepRefList({ refs }: { refs: StepRef[] }) {
  if (refs.length === 0) return null;
  return (
    <div>
      <Tooltip text="Session steps where this pattern appears">
        <div className="flex items-center gap-1.5 text-xs text-zinc-400 mb-2 cursor-help">
          <BookOpen className="w-3.5 h-3.5" />
          <span className="font-semibold">Evidence</span>
          <span className="text-zinc-600">({refs.length} step{refs.length !== 1 ? "s" : ""})</span>
        </div>
      </Tooltip>
      <div className="flex items-center gap-2 flex-wrap">
        {refs.map((stepRef, i) => (
          <JumpToStepButton key={i} stepRef={stepRef} />
        ))}
      </div>
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
        className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-md bg-zinc-700/50 text-zinc-300 hover:bg-teal-900/40 hover:text-teal-300 transition font-mono border border-zinc-600/30 hover:border-teal-700/30"
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
  fetchWithToken,
  agentSources,
}: {
  recommendations: SkillRecommendation[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  return (
    <section>
      <SectionHeader
        icon={<Search className="w-5 h-5" />}
        title="Discovered Skills"
        tooltip="Catalog skills matching your workflow"
      />
      <div className="space-y-3">
        {recommendations.map((rec) => (
          <RecommendationCard
            key={rec.skill_name}
            rec={rec}
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
  fetchWithToken,
  agentSources,
}: {
  rec: SkillRecommendation;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [installed, setInstalled] = useState(false);

  const confidencePct = Math.round(rec.confidence * 100);
  const isHigh = rec.confidence >= CONFIDENCE_THRESHOLDS.HIGH;
  const isMedium = rec.confidence >= CONFIDENCE_THRESHOLDS.MEDIUM;
  const barColor = isHigh ? "bg-emerald-500" : isMedium ? "bg-amber-500" : "bg-zinc-600";
  const textColor = isHigh ? "text-emerald-400" : isMedium ? "text-amber-400" : "text-zinc-500";
  const borderColor = isHigh ? "border-emerald-700/30" : isMedium ? "border-amber-700/30" : "border-zinc-700/50";

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
    <div className={`border ${borderColor} rounded-xl bg-zinc-800/40 overflow-hidden`}>
      <div className="px-5 py-4">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2.5">
            <div className={`p-1.5 rounded-lg ${isHigh ? "bg-emerald-600/15" : isMedium ? "bg-amber-600/15" : "bg-zinc-700/40"}`}>
              <Lightbulb className={`w-4 h-4 ${textColor}`} />
            </div>
            <span className="font-mono text-sm font-bold text-zinc-100">{rec.skill_name}</span>
          </div>
          <div className="flex items-center gap-2.5">
            <Tooltip text={`${confidencePct}% match to your patterns`}>
              <div className="flex items-center gap-2 cursor-help">
                <div className="w-16 h-1.5 rounded-full bg-zinc-700/60 overflow-hidden">
                  <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${confidencePct}%` }} />
                </div>
                <span className={`text-xs font-semibold ${textColor} tabular-nums`}>{confidencePct}%</span>
              </div>
            </Tooltip>
            {installed ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-teal-300 bg-teal-900/30 rounded-lg border border-teal-700/20">
                <Check className="w-3.5 h-3.5" /> Installed
              </span>
            ) : (
              <Tooltip text="Preview and install skill">
                <button
                  onClick={handlePreview}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition"
                >
                  <Eye className="w-3.5 h-3.5" />
                  Preview &amp; Install
                </button>
              </Tooltip>
            )}
          </div>
        </div>
        <p className="text-sm text-zinc-400 leading-relaxed pl-[2.375rem]">{rec.rationale}</p>
      </div>
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
    </div>
  );
}

/* ── Generated Skills (Create) ── */

function CreationSection({
  skills,
  fetchWithToken,
  agentSources,
}: {
  skills: SkillCreation[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  return (
    <section>
      <SectionHeader
        icon={<Sparkles className="w-5 h-5" />}
        title="Custom Skills"
        tooltip="Generated skills from your patterns"
        accentColor="text-emerald-400"
      />
      <div className="space-y-3">
        {skills.map((skill) => (
          <CreatedSkillCard
            key={skill.name}
            skill={skill}
            fetchWithToken={fetchWithToken}
            agentSources={agentSources}
          />
        ))}
      </div>
    </section>
  );
}

function ConfidenceBar({ confidence, accentColor = "emerald" }: { confidence: number; accentColor?: "emerald" | "amber" }) {
  const pct = Math.round(confidence * 100);
  const isHigh = confidence >= CONFIDENCE_THRESHOLDS.HIGH;
  const isMedium = confidence >= CONFIDENCE_THRESHOLDS.MEDIUM;

  const barColor = isHigh
    ? (accentColor === "amber" ? "bg-amber-500" : "bg-emerald-500")
    : isMedium ? "bg-amber-500" : "bg-zinc-600";
  const textColor = isHigh
    ? (accentColor === "amber" ? "text-amber-400" : "text-emerald-400")
    : isMedium ? "text-amber-400" : "text-zinc-500";

  return (
    <Tooltip text={`${pct}% confidence`}>
      <div className="flex items-center gap-2 cursor-help">
        <div className="w-16 h-1.5 rounded-full bg-zinc-700/60 overflow-hidden">
          <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-xs font-semibold ${textColor} tabular-nums`}>{pct}%</span>
      </div>
    </Tooltip>
  );
}

function CreatedSkillCard({
  skill,
  fetchWithToken,
  agentSources,
}: {
  skill: SkillCreation;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const [showPreview, setShowPreview] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [editedContent, setEditedContent] = useState(skill.skill_md_content);

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
    <div className="border border-emerald-700/30 rounded-xl bg-emerald-950/15 overflow-hidden">
      <div className="px-5 py-4">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-emerald-600/15">
              <FileCode className="w-4 h-4 text-emerald-400" />
            </div>
            <span className="font-mono text-sm font-bold text-zinc-100">{skill.name}</span>
            {skill.confidence > 0 && <ConfidenceBar confidence={skill.confidence} />}
          </div>
          <div className="flex items-center gap-2">
            {installed ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-emerald-300 bg-emerald-900/30 rounded-lg border border-emerald-700/20">
                <Check className="w-3.5 h-3.5" /> Installed
              </span>
            ) : (
              <Tooltip text="Preview and install skill">
                <button
                  onClick={() => setShowPreview(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg transition"
                >
                  <Eye className="w-3.5 h-3.5" />
                  Preview &amp; Install
                </button>
              </Tooltip>
            )}
          </div>
        </div>
        <p className="text-sm text-zinc-300 leading-relaxed pl-[2.375rem]">{skill.description}</p>
        <div className="mt-2.5 pl-[2.375rem]">
          <div className="flex items-center gap-1.5 mb-1">
            <Lightbulb className="w-3 h-3 text-emerald-500/60 shrink-0" />
            <span className="text-xs font-semibold text-emerald-400/70">Why this is useful</span>
          </div>
          <p className="text-sm text-emerald-300/80 leading-relaxed pl-[1.125rem]">{skill.rationale}</p>
        </div>
      </div>
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
    </div>
  );
}

/* ── Evolution Suggestions (Evolve) ── */

function EvolutionSection({
  suggestions,
  fetchWithToken,
  agentSources,
}: {
  suggestions: SkillEvolution[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  return (
    <section>
      <SectionHeader
        icon={<TrendingUp className="w-5 h-5" />}
        title="Evolution Suggestions"
        tooltip="Targeted improvements for your installed skills based on real usage"
        accentColor="text-amber-400"
      />
      <div className="space-y-3">
        {suggestions.map((sug) => (
          <EvolutionCard
            key={sug.skill_name}
            suggestion={sug}
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
  fetchWithToken,
  agentSources,
}: {
  suggestion: SkillEvolution;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const [expanded, setExpanded] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
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
    <div className="border border-amber-700/30 rounded-xl bg-amber-950/15 overflow-hidden">
      <div className="flex items-start px-5 py-4">
        <button onClick={handleExpand} className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2.5 mb-2">
            <div className="p-1.5 rounded-lg bg-amber-600/15">
              <TrendingUp className="w-4 h-4 text-amber-400" />
            </div>
            <span className="font-mono text-sm font-bold text-zinc-100">{suggestion.skill_name}</span>
            <Tooltip text={`${suggestion.edits.length} edit${suggestion.edits.length !== 1 ? "s" : ""} suggested`}>
              <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-900/30 text-amber-300 border border-amber-700/20 cursor-help">
                <Pencil className="w-2.5 h-2.5" />
                {suggestion.edits.length} edit{suggestion.edits.length !== 1 ? "s" : ""}
              </span>
            </Tooltip>
            {suggestion.confidence > 0 && <ConfidenceBar confidence={suggestion.confidence} accentColor="amber" />}
          </div>
          <p className="text-sm text-zinc-100 leading-relaxed pl-[2.375rem]">{suggestion.rationale}</p>
        </button>
        <div className="flex items-center gap-2 shrink-0 ml-3">
          {updated ? (
            <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-amber-300 bg-amber-900/30 rounded-lg border border-amber-700/20">
              <Check className="w-3.5 h-3.5" /> Updated
            </span>
          ) : (
            <Tooltip text="Preview merged result">
              <button
                onClick={handlePreview}
                disabled={loadingOriginal}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 rounded-lg transition disabled:opacity-50"
              >
                {loadingOriginal
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Eye className="w-3.5 h-3.5" />}
                Preview &amp; Update
              </button>
            </Tooltip>
          )}
          {fetchError && (
            <span className="text-xs text-red-400">{fetchError}</span>
          )}
          <button onClick={handleExpand} className="p-1 text-zinc-500 hover:text-zinc-300 transition">
            {expanded
              ? <ChevronDown className="w-4 h-4" />
              : <ChevronRight className="w-4 h-4" />}
          </button>
        </div>
      </div>
      {expanded && suggestion.edits.length > 0 && (
        <div className="border-t border-amber-800/20 px-5 py-4 bg-zinc-900/20 space-y-4">
          <EvolutionDiffView
            skillName={suggestion.skill_name}
            edits={suggestion.edits}
            originalContent={originalContent ?? undefined}
          />
        </div>
      )}
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
    </div>
  );
}

