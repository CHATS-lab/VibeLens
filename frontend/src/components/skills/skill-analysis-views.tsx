import {
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Download,
  FileCode,
  GitBranch,
  Lightbulb,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Repeat,
  RotateCcw,
  Search,
  Shield,
  Sparkles,
  Target,
  TrendingUp,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type {
  SkillAnalysisResult,
  SkillCreation,
  SkillEvolutionSuggestion,
  SkillMode,
  SkillRecommendation,
  SkillSourceInfo,
  StepRef,
  WorkflowPattern,
} from "../../types";
import { DemoBanner } from "../demo-banner";
import { Tooltip } from "../tooltip";
import { WarningsBanner } from "../warnings-banner";
import { InstallTargetDialog } from "./install-target-dialog";
import { applySkillEdits } from "./skill-edit-utils";
import { EvolutionDiffView } from "./skill-evolution-diff";
import { SkillUpdateDialog } from "./skill-update-dialog";

export type SkillTab = "local" | "explore" | "retrieve" | "create" | "evolve";

const CONFIDENCE_THRESHOLDS = { HIGH: 0.75, MEDIUM: 0.5 } as const;

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
        <p className="text-sm text-zinc-500 mt-1.5">{MODE_SUBLABELS[mode]}</p>
      </div>
    </div>
  );
}

export function AnalysisResultView({
  result,
  activeTab,
  onRerun,
  onNew,
  fetchWithToken,
}: {
  result: SkillAnalysisResult;
  activeTab: SkillTab;
  onRerun: () => void;
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
      <ResultHeader result={result} onRerun={onRerun} onNew={onNew} />
      {result.warnings && result.warnings.length > 0 && (
        <WarningsBanner warnings={result.warnings} />
      )}

      {/* Summary card */}
      <SummaryCard summary={result.summary} userProfile={result.user_profile} />

      {/* Recommended Skills (Recommend) */}
      {activeTab === "retrieve" && result.recommendations.length > 0 && (
        <RecommendationSection recommendations={result.recommendations} />
      )}

      {/* Generated Skills (Create) */}
      {activeTab === "create" && result.generated_skills.length > 0 && (
        <CreationSection
          skills={result.generated_skills}
          fetchWithToken={fetchWithToken}
          agentSources={agentSources}
        />
      )}

      {/* Evolution Suggestions (Evolve) */}
      {activeTab === "evolve" && result.evolution_suggestions.length > 0 && (
        <EvolutionSection
          suggestions={result.evolution_suggestions}
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
  onRerun,
  onNew,
}: {
  result: SkillAnalysisResult;
  onRerun: () => void;
  onNew: () => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <BarChart3 className="w-6 h-6 text-teal-400" />
        <div>
          <h2 className="text-xl font-bold text-zinc-100">
            {result.workflow_patterns.length} pattern{result.workflow_patterns.length !== 1 ? "s" : ""} detected
          </h2>
          <p className="text-sm text-zinc-400">
            {result.session_ids.length} session{result.session_ids.length !== 1 ? "s" : ""} analyzed
            {result.sessions_skipped.length > 0 && (
              <span className="text-zinc-500">
                {" "}&middot; {result.sessions_skipped.length} skipped
              </span>
            )}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onNew}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
        >
          <Plus className="w-3 h-3" /> New
        </button>
        <button
          onClick={onRerun}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-teal-600 hover:bg-teal-500 rounded-md transition"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Re-run
        </button>
      </div>
    </div>
  );
}

function SummaryCard({ summary, userProfile }: { summary: string; userProfile: string }) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-5 space-y-3">
      <p className="text-sm text-zinc-200 leading-relaxed">{summary}</p>
      {userProfile && (
        <div className="flex items-start gap-2 pt-3 border-t border-zinc-700/40">
          <Shield className="w-3.5 h-3.5 text-zinc-500 mt-0.5 shrink-0" />
          <p className="text-sm text-zinc-200 italic leading-relaxed">{userProfile}</p>
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

function MetadataFooter({ result }: { result: SkillAnalysisResult }) {
  const computedDate = new Date(result.created_at);
  const dateStr = isNaN(computedDate.getTime()) ? result.created_at : computedDate.toLocaleDateString();
  const timeStr = isNaN(computedDate.getTime()) ? "" : computedDate.toLocaleTimeString();

  return (
    <Tooltip text="Inference backend, model, and estimated API cost for this analysis run">
      <div className="border-t border-zinc-800 pt-4 text-xs text-zinc-500 flex items-center justify-between gap-4 w-full cursor-help">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{result.backend_id}/{result.model}</span>
          {result.cost_usd != null && (
            <span className="border-l border-zinc-700 pl-2">
              ${result.cost_usd.toFixed(4)}
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
        tooltip="Recurring tool sequences and task types detected across your sessions. Each pattern is a potential skill opportunity."
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
            <Tooltip text={`Observed ${pattern.frequency} time${pattern.frequency !== 1 ? "s" : ""} across sessions`}>
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
          {/* Pain Point */}
          <div className="rounded-lg bg-amber-950/15 border border-amber-800/20 px-4 py-3">
            <Tooltip text="The reason this workflow is suboptimal and could benefit from automation">
              <div className="flex items-center gap-1.5 text-xs text-amber-400/80 mb-1.5 cursor-help">
                <Zap className="w-3.5 h-3.5" />
                <span className="font-semibold uppercase tracking-wider">Pain Point</span>
              </div>
            </Tooltip>
            <p className="text-sm text-amber-200/80 leading-relaxed">{pattern.pain_point}</p>
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
      <Tooltip text="Steps in the session transcripts where this pattern was observed">
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
    <Tooltip text={`Jump to step ${stepRef.start_step_id.slice(0, 12)} in session viewer`}>
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

function RecommendationSection({ recommendations }: { recommendations: SkillRecommendation[] }) {
  return (
    <section>
      <SectionHeader
        icon={<Search className="w-5 h-5" />}
        title="Discovered Skills"
        tooltip="Pre-built skills from the catalog that match your workflow patterns"
      />
      <div className="space-y-3">
        {recommendations.map((rec) => <RecommendationCard key={rec.skill_name} rec={rec} />)}
      </div>
    </section>
  );
}

function RecommendationCard({ rec }: { rec: SkillRecommendation }) {
  const confidencePct = Math.round(rec.confidence * 100);
  const isHigh = rec.confidence >= CONFIDENCE_THRESHOLDS.HIGH;
  const isMedium = rec.confidence >= CONFIDENCE_THRESHOLDS.MEDIUM;
  const barColor = isHigh ? "bg-emerald-500" : isMedium ? "bg-amber-500" : "bg-zinc-600";
  const textColor = isHigh ? "text-emerald-400" : isMedium ? "text-amber-400" : "text-zinc-500";
  const borderColor = isHigh ? "border-emerald-700/30" : isMedium ? "border-amber-700/30" : "border-zinc-700/50";

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
          <Tooltip text={`How well this skill matches your detected patterns (${confidencePct}%)`}>
            <div className="flex items-center gap-2 cursor-help">
              <div className="w-16 h-1.5 rounded-full bg-zinc-700/60 overflow-hidden">
                <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${confidencePct}%` }} />
              </div>
              <span className={`text-xs font-semibold ${textColor} tabular-nums`}>{confidencePct}%</span>
            </div>
          </Tooltip>
        </div>
        <p className="text-sm text-zinc-400 leading-relaxed pl-[2.375rem]">{rec.match_reason}</p>
      </div>
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
        tooltip="New SKILL.md files generated from your workflow patterns"
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

function CreatedSkillCard({
  skill,
  fetchWithToken,
  agentSources,
}: {
  skill: SkillCreation;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const [expanded, setExpanded] = useState(false);
  const [showInstallDialog, setShowInstallDialog] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [editedContent, setEditedContent] = useState<string | null>(null);

  const activeContent = editedContent ?? skill.skill_md_content;

  const handleInstall = useCallback(
    async (targets: string[]) => {
      try {
        const res = await fetchWithToken("/api/skills/install", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: skill.name, content: activeContent }),
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
      setShowInstallDialog(false);
    },
    [fetchWithToken, skill, activeContent],
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
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition px-2.5 py-1 rounded-md hover:bg-zinc-800 border border-zinc-700/30"
            >
              <Code2 className="w-3 h-3" />
              {expanded ? "Hide" : "Preview"}
            </button>
            <Tooltip text="Install this skill to your agent interfaces">
              <button
                onClick={() => setShowInstallDialog(true)}
                disabled={installed}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg transition disabled:opacity-50"
              >
                {installed
                  ? (<><Check className="w-3.5 h-3.5" /> Installed</>)
                  : (<><Download className="w-3.5 h-3.5" /> Install</>)}
              </button>
            </Tooltip>
          </div>
        </div>
        <p className="text-sm text-zinc-300 leading-relaxed pl-[2.375rem]">{skill.description}</p>
        <div className="flex items-start gap-1.5 mt-2.5 pl-[2.375rem]">
          <Lightbulb className="w-3 h-3 text-emerald-500/60 mt-0.5 shrink-0" />
          <p className="text-sm text-emerald-300/80 italic leading-relaxed">{skill.rationale}</p>
        </div>
      </div>
      {expanded && (
        <div className="border-t border-emerald-800/20 px-5 py-4 bg-zinc-900/30 space-y-2">
          <textarea
            value={activeContent}
            onChange={(e) => setEditedContent(e.target.value)}
            className="w-full min-h-[200px] max-h-72 bg-zinc-900/80 text-zinc-300 text-xs font-mono rounded-lg p-4 border border-zinc-800/50 focus:border-emerald-600/50 focus:outline-none resize-y whitespace-pre-wrap leading-relaxed"
            spellCheck={false}
          />
          {editedContent !== null && (
            <button
              onClick={() => setEditedContent(null)}
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition px-2 py-1 rounded-md hover:bg-zinc-800 border border-zinc-700/30"
            >
              <RotateCcw className="w-3 h-3" /> Reset
            </button>
          )}
        </div>
      )}
      {showInstallDialog && (
        <InstallTargetDialog
          skillName={skill.name}
          agentSources={agentSources}
          onInstall={handleInstall}
          onCancel={() => setShowInstallDialog(false)}
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
  suggestions: SkillEvolutionSuggestion[];
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
  suggestion: SkillEvolutionSuggestion;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const [expanded, setExpanded] = useState(false);
  const [showUpdateDialog, setShowUpdateDialog] = useState(false);
  const [mergedContent, setMergedContent] = useState<string | null>(null);
  const [loadingOriginal, setLoadingOriginal] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [updated, setUpdated] = useState(false);

  const handleApplyAndEdit = useCallback(async () => {
    setLoadingOriginal(true);
    setFetchError(null);
    try {
      const res = await fetchWithToken(`/api/skills/local/${suggestion.skill_name}`);
      if (res.status === 404) {
        setFetchError("Skill not found in central store");
        return;
      }
      if (!res.ok) {
        setFetchError("Failed to fetch skill content");
        return;
      }
      const data = await res.json();
      const merged = applySkillEdits(data.content, suggestion.edits);
      setMergedContent(merged);
      setShowUpdateDialog(true);
    } catch {
      setFetchError("Network error fetching skill");
    } finally {
      setLoadingOriginal(false);
    }
  }, [fetchWithToken, suggestion]);

  const handleUpdate = useCallback(async (content: string, targets: string[]) => {
    setUpdating(true);
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
    } finally {
      setUpdating(false);
      setShowUpdateDialog(false);
    }
  }, [fetchWithToken, suggestion.skill_name]);

  return (
    <div className="border border-amber-700/30 rounded-xl bg-amber-950/15 overflow-hidden">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left px-5 py-4">
        <div className="flex items-center gap-2.5 mb-2">
          <div className="p-1.5 rounded-lg bg-amber-600/15">
            <TrendingUp className="w-4 h-4 text-amber-400" />
          </div>
          <span className="font-mono text-sm font-bold text-zinc-100">{suggestion.skill_name}</span>
          <Tooltip text={`${suggestion.edits.length} specific edit(s) suggested for this skill`}>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-900/30 text-amber-300 border border-amber-700/20 cursor-help">
              <Pencil className="w-2.5 h-2.5" />
              {suggestion.edits.length} edit{suggestion.edits.length !== 1 ? "s" : ""}
            </span>
          </Tooltip>
          <div className="flex-1" />
          {expanded
            ? <ChevronDown className="w-4 h-4 text-zinc-500" />
            : <ChevronRight className="w-4 h-4 text-zinc-500" />}
        </div>
        <p className="text-sm text-zinc-100 leading-relaxed pl-[2.375rem]">{suggestion.rationale}</p>
      </button>
      {expanded && suggestion.edits.length > 0 && (
        <div className="border-t border-amber-800/20 px-5 py-4 bg-zinc-900/20 space-y-4">
          {/* Apply & Edit action row */}
          <div className="flex items-center gap-2">
            {updated ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-amber-300 bg-amber-900/30 rounded-lg border border-amber-700/20">
                <Check className="w-3.5 h-3.5" /> Updated
              </span>
            ) : (
              <button
                onClick={(e) => { e.stopPropagation(); handleApplyAndEdit(); }}
                disabled={loadingOriginal}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 rounded-lg transition disabled:opacity-50"
              >
                {loadingOriginal
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Pencil className="w-3.5 h-3.5" />}
                Apply &amp; Edit
              </button>
            )}
            {fetchError && (
              <span className="text-xs text-red-400">{fetchError}</span>
            )}
          </div>

          <EvolutionDiffView skillName={suggestion.skill_name} edits={suggestion.edits} />
        </div>
      )}
      {showUpdateDialog && mergedContent !== null && (
        <SkillUpdateDialog
          skillName={suggestion.skill_name}
          initialContent={mergedContent}
          agentSources={agentSources}
          onUpdate={handleUpdate}
          onCancel={() => setShowUpdateDialog(false)}
          updating={updating}
        />
      )}
    </div>
  );
}

