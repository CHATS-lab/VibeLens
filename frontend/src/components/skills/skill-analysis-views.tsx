import {
  AlertCircle,
  ArrowRight,
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
  Layers,
  Lightbulb,
  Loader2,
  MessageSquare,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Repeat,
  Search,
  Shield,
  Sparkles,
  Target,
  TrendingUp,
  Wrench,
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
import { Tooltip } from "../tooltip";
import { InstallTargetDialog } from "./install-target-dialog";

export type SkillTab = "local" | "explore" | "retrieve" | "create" | "evolve";

const CONFIDENCE_THRESHOLDS = { HIGH: 0.75, MEDIUM: 0.5 } as const;

export function AnalysisLoadingState({ mode, sessionCount }: { mode: SkillMode; sessionCount: number }) {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-5">
        <div className="relative">
          <div className="absolute inset-0 rounded-full bg-teal-500/20 animate-ping" />
          <Loader2 className="w-12 h-12 text-teal-400 animate-spin relative" />
        </div>
        <div className="text-center">
          <p className="text-base font-semibold text-zinc-100">
            Analyzing {sessionCount} session{sessionCount !== 1 ? "s" : ""}
          </p>
          <p className="text-sm text-zinc-500 mt-1.5">Mode: {mode} — detecting workflow patterns</p>
        </div>
      </div>
    </div>
  );
}

export function AnalysisEmptyState({
  mode,
  checkedCount,
  error,
  onRun,
}: {
  mode: SkillMode;
  checkedCount: number;
  error: string | null;
  onRun: () => void;
}) {
  const modeDescriptions: Record<SkillMode, { title: string; desc: string; icon: React.ReactNode }> = {
    retrieval: {
      title: "Skill Retrieval",
      desc: "Detect workflow patterns and recommend existing skills that match your coding style.",
      icon: <Search className="w-8 h-8 text-teal-400" />,
    },
    creation: {
      title: "Skill Creation",
      desc: "Generate new SKILL.md files from detected automation opportunities in your sessions.",
      icon: <Sparkles className="w-8 h-8 text-emerald-400" />,
    },
    evolution: {
      title: "Skill Evolution",
      desc: "Analyze installed skills against your usage data and suggest targeted improvements.",
      icon: <TrendingUp className="w-8 h-8 text-amber-400" />,
    },
  };
  const info = modeDescriptions[mode];

  return (
    <div className="flex items-center justify-center h-full">
      <div className="max-w-md text-center px-6">
        <div className="flex justify-center mb-5">{info.icon}</div>
        <h3 className="text-xl font-bold text-zinc-100 mb-3">{info.title}</h3>
        <p className="text-sm text-zinc-400 mb-6 leading-relaxed">{info.desc}</p>
        {error && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-red-900/20 border border-red-800/30 mb-4 text-left">
            <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}
        <button
          onClick={onRun}
          disabled={checkedCount === 0}
          className="inline-flex items-center gap-2 px-6 py-3 text-sm font-semibold text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Play className="w-4 h-4" />
          {checkedCount > 0
            ? `Analyze ${checkedCount} session${checkedCount !== 1 ? "s" : ""}`
            : "Select sessions first"}
        </button>
        {checkedCount === 0 && (
          <p className="text-xs text-zinc-600 mt-3">
            Use the checkboxes in the session list to select sessions for analysis.
          </p>
        )}
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
      {/* Header */}
      <ResultHeader result={result} onRerun={onRerun} onNew={onNew} />

      {/* Summary card */}
      <SummaryCard summary={result.summary} userProfile={result.user_profile} />

      {/* Workflow Patterns — always shown */}
      {result.workflow_patterns.length > 0 && (
        <PatternSection patterns={result.workflow_patterns} />
      )}

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
        <EvolutionSection suggestions={result.evolution_suggestions} />
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
        <div className="p-2 rounded-lg bg-teal-600/20">
          <BarChart3 className="w-5 h-5 text-teal-400" />
        </div>
        <div>
          <h3 className="text-base font-bold text-zinc-100">
            {result.workflow_patterns.length} pattern{result.workflow_patterns.length !== 1 ? "s" : ""} detected
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {result.session_ids.length} session{result.session_ids.length !== 1 ? "s" : ""} analyzed
            {result.sessions_skipped.length > 0 && ` · ${result.sessions_skipped.length} skipped`}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onNew}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 rounded-md transition"
        >
          <Plus className="w-3.5 h-3.5" /> New
        </button>
        <button
          onClick={onRerun}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-teal-600 hover:bg-teal-500 rounded-md transition"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Re-run
        </button>
      </div>
    </div>
  );
}

function SummaryCard({ summary, userProfile }: { summary: string; userProfile: string }) {
  return (
    <div className="relative overflow-hidden rounded-xl bg-zinc-800/50 border border-zinc-700/30">
      <div className="absolute inset-0 bg-gradient-to-br from-teal-900/10 via-transparent to-transparent" />
      <div className="relative p-5">
        <div className="flex items-center gap-2 mb-3">
          <MessageSquare className="w-4 h-4 text-teal-400" />
          <span className="text-xs font-semibold text-teal-400 uppercase tracking-wider">Analysis Summary</span>
        </div>
        <p className="text-sm text-zinc-300 leading-relaxed">{summary}</p>
        {userProfile && (
          <div className="flex items-start gap-2 mt-3 pt-3 border-t border-zinc-700/30">
            <Shield className="w-3.5 h-3.5 text-zinc-500 mt-0.5 shrink-0" />
            <p className="text-xs text-zinc-500 italic">{userProfile}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function SectionHeader({
  icon,
  title,
  tooltip,
  count,
  accentColor = "text-teal-400",
}: {
  icon: React.ReactNode;
  title: string;
  tooltip: string;
  count?: number;
  accentColor?: string;
}) {
  return (
    <div className="flex items-center gap-2.5 mb-4">
      <Tooltip text={tooltip}>
        <span className={accentColor}>{icon}</span>
      </Tooltip>
      <Tooltip text={tooltip}>
        <h4 className="text-base font-bold text-zinc-100 cursor-help">{title}</h4>
      </Tooltip>
      {count != null && (
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-zinc-700/60 text-zinc-400">
          {count}
        </span>
      )}
    </div>
  );
}

function MetadataFooter({ result }: { result: SkillAnalysisResult }) {
  return (
    <div className="flex items-center gap-4 text-xs text-zinc-600 pt-4 border-t border-zinc-800">
      <div className="flex items-center gap-1.5">
        <Layers className="w-3 h-3" />
        <span>{result.backend_id}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Code2 className="w-3 h-3" />
        <span>{result.model}</span>
      </div>
      {result.cost_usd != null && (
        <span>${result.cost_usd.toFixed(4)}</span>
      )}
      <span>{new Date(result.created_at).toLocaleString()}</span>
    </div>
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
        count={patterns.length}
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
          <p className="text-xs text-zinc-400 leading-relaxed mt-1">{pattern.description}</p>
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
        title="Recommended Skills"
        tooltip="Pre-built skills from the catalog that match your workflow patterns"
        count={recommendations.length}
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
        title="Generated Skills"
        tooltip="New SKILL.md files generated from your workflow patterns"
        count={skills.length}
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

  const handleInstall = useCallback(
    async (targets: string[]) => {
      try {
        const res = await fetchWithToken("/api/skills/install", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: skill.name, content: skill.skill_md_content }),
        });
        if (!res.ok) return;

        // Sync to selected agent interfaces
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
    [fetchWithToken, skill],
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
          <p className="text-xs text-emerald-400/60 italic">{skill.rationale}</p>
        </div>
      </div>
      {expanded && (
        <div className="border-t border-emerald-800/20 px-5 py-4 bg-zinc-900/30">
          <pre className="text-xs text-zinc-300 font-mono bg-zinc-900/80 rounded-lg p-4 overflow-x-auto max-h-72 overflow-y-auto whitespace-pre-wrap leading-relaxed border border-zinc-800/50">
            {skill.skill_md_content}
          </pre>
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

function EvolutionSection({ suggestions }: { suggestions: SkillEvolutionSuggestion[] }) {
  return (
    <section>
      <SectionHeader
        icon={<TrendingUp className="w-5 h-5" />}
        title="Evolution Suggestions"
        tooltip="Targeted improvements for your installed skills based on real usage"
        count={suggestions.length}
        accentColor="text-amber-400"
      />
      <div className="space-y-3">
        {suggestions.map((sug) => <EvolutionCard key={sug.skill_name} suggestion={sug} />)}
      </div>
    </section>
  );
}

function EvolutionCard({ suggestion }: { suggestion: SkillEvolutionSuggestion }) {
  const [expanded, setExpanded] = useState(false);
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
        <p className="text-sm text-zinc-400 leading-relaxed pl-[2.375rem]">{suggestion.rationale}</p>
      </button>
      {expanded && suggestion.edits.length > 0 && (
        <div className="border-t border-amber-800/20 px-5 py-4 space-y-3 bg-zinc-900/20">
          {suggestion.edits.map((edit, i) => (
            <div key={i} className="flex items-start gap-3 text-sm pl-[2.375rem]">
              <Tooltip text={EDIT_KIND_DESCRIPTIONS[edit.kind] || "A specific edit to the skill definition"}>
                <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-md shrink-0 mt-0.5 cursor-help ${EDIT_KIND_STYLES[edit.kind] || "bg-zinc-700/80 text-zinc-300"}`}>
                  {EDIT_KIND_ICONS[edit.kind] || <Pencil className="w-2.5 h-2.5" />}
                  {EDIT_KIND_LABELS[edit.kind] || edit.kind}
                </span>
              </Tooltip>
              <div className="min-w-0">
                <p className="text-zinc-200">{edit.target}</p>
                {edit.replacement && (
                  <div className="flex items-center gap-1.5 mt-1 text-emerald-400">
                    <ArrowRight className="w-3 h-3 shrink-0" />
                    <p className="text-sm">{edit.replacement}</p>
                  </div>
                )}
                <p className="text-xs text-zinc-500 italic mt-1">{edit.rationale}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const EDIT_KIND_DESCRIPTIONS: Record<string, string> = {
  add_instruction: "Add a new step or instruction to the skill body",
  remove_instruction: "Remove an outdated or counterproductive instruction",
  replace_instruction: "Replace an existing instruction with an improved version",
  update_description: "Change the skill's trigger description for better activation",
  add_tool: "Add a tool to the skill's allowed tools list",
  remove_tool: "Remove an unnecessary tool from the allowed tools list",
};

const EDIT_KIND_LABELS: Record<string, string> = {
  add_instruction: "Add",
  remove_instruction: "Remove",
  replace_instruction: "Replace",
  update_description: "Update",
  add_tool: "Add Tool",
  remove_tool: "Remove Tool",
};

const EDIT_KIND_STYLES: Record<string, string> = {
  add_instruction: "bg-emerald-900/30 text-emerald-400 border border-emerald-700/20",
  remove_instruction: "bg-red-900/30 text-red-400 border border-red-700/20",
  replace_instruction: "bg-sky-900/30 text-sky-400 border border-sky-700/20",
  update_description: "bg-amber-900/30 text-amber-400 border border-amber-700/20",
  add_tool: "bg-teal-900/30 text-teal-400 border border-teal-700/20",
  remove_tool: "bg-rose-900/30 text-rose-400 border border-rose-700/20",
};

const EDIT_KIND_ICONS: Record<string, React.ReactNode> = {
  add_instruction: <Plus className="w-2.5 h-2.5" />,
  remove_instruction: <Zap className="w-2.5 h-2.5" />,
  replace_instruction: <ArrowRight className="w-2.5 h-2.5" />,
  update_description: <Pencil className="w-2.5 h-2.5" />,
  add_tool: <Wrench className="w-2.5 h-2.5" />,
  remove_tool: <Wrench className="w-2.5 h-2.5" />,
};
