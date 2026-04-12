import {
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  Lightbulb,
  Loader2,
  Pencil,
  Target,
  TrendingUp,
} from "lucide-react";
import { useCallback, useState } from "react";
import type {
  SkillEvolution,
  SkillSourceInfo,
  WorkflowPattern,
} from "../../types";
import { BulletText } from "../bullet-text";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { Tooltip } from "../tooltip";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import { ConfidenceBar, SectionHeader } from "./skill-shared";
import { StepRefList } from "./skill-patterns-view";
import { applySkillEdits } from "./skill-edit-utils";
import { EvolutionDiffView } from "./skill-evolution-diff";
import { SkillPreviewDialog } from "./skill-preview-dialog";

export function EvolutionSection({
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
