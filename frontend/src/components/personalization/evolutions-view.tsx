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
  Evolution,
  SkillSyncTarget,
  WorkflowPattern,
} from "../../types";
import { useExtensionsClient } from "../../app";
import { BulletText } from "../ui/bullet-text";
import { CollapsibleText } from "../ui/collapsible-text";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { Tooltip } from "../ui/tooltip";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import { ConfidenceBar, SectionHeader } from "./result-shared";
import { StepRefList } from "./patterns-view";
import { applyEdits } from "./edit-utils";
import { EvolutionDiffView } from "./evolution-diff";
import { PreviewDialog } from "./preview-dialog";

export function EvolutionSection({
  suggestions,
  workflowPatterns,
  syncTargets,
  onInstalled,
}: {
  suggestions: Evolution[];
  workflowPatterns: WorkflowPattern[];
  syncTargets: SkillSyncTarget[];
  onInstalled?: () => void;
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
            key={sug.element_name}
            suggestion={sug}
            workflowPatterns={workflowPatterns}
            syncTargets={syncTargets}
            onInstalled={onInstalled}
          />
        ))}
      </div>
    </section>
  );
}

function EvolutionCard({
  suggestion,
  workflowPatterns,
  syncTargets,
  onInstalled,
}: {
  suggestion: Evolution;
  workflowPatterns: WorkflowPattern[];
  syncTargets: SkillSyncTarget[];
  onInstalled?: () => void;
}) {
  const client = useExtensionsClient();
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [expanded, setExpanded] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [rationaleExpanded, setRationaleExpanded] = useState(false);
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
      const data = await client.skills.get(suggestion.element_name);
      setOriginalContent(data.content);
      return data.content;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setFetchError(msg.includes("not found") ? "Skill not found in central store" : "Failed to fetch skill content");
      return null;
    } finally {
      setLoadingOriginal(false);
    }
  }, [client, suggestion.element_name, originalContent]);

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
    const merged = applyEdits(content, suggestion.edits);
    setMergedContent(merged);
    setShowPreview(true);
  }, [fetchOriginal, suggestion.edits]);

  const handleUpdate = useCallback(async (content: string, targets: string[]) => {
    try {
      await client.skills.modify(suggestion.element_name, content);
      if (targets.length > 0) {
        await client.skills.syncToAgents(suggestion.element_name, targets);
      }
      setUpdated(true);
      onInstalled?.();
    } catch {
      /* ignore */
    }
    setShowPreview(false);
  }, [client, suggestion.element_name, onInstalled]);

  return (
    <div className="border border-default rounded-xl bg-subtle overflow-hidden">
      {/* Header: Name + Badges + Confidence + Action */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-base font-bold text-primary">{suggestion.element_name}</span>
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
              <Tooltip text="Updated — click to re-open and adjust sync targets">
                <button
                  onClick={() => guardAction(handlePreview)}
                  disabled={loadingOriginal}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-emerald bg-accent-emerald-subtle hover:bg-emerald-100 dark:hover:bg-emerald-900/25 rounded-lg border border-accent-emerald-border transition disabled:opacity-50"
                >
                  {loadingOriginal
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Check className="w-3.5 h-3.5" />}
                  Updated
                </button>
              </Tooltip>
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
            {fetchError && <span className="text-xs text-accent-rose">{fetchError}</span>}
          </div>
        </div>
      </div>
      {suggestion.description && (
        <CollapsibleText
          text={suggestion.description}
          label="Description:"
          className="px-5 pb-3 text-sm text-secondary leading-relaxed"
        />
      )}

      {/* Proposed Edits */}
      <div className="px-5 py-3 border-t border-default">
        <button
          onClick={handleExpand}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {expanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
          <Pencil className="w-3.5 h-3.5 text-accent-teal" />
          <span className="text-sm font-semibold text-accent-teal tracking-wide">Proposed Edits</span>
          <span className="text-dimmed">({suggestion.edits.length})</span>
        </button>
        {expanded && suggestion.edits.length > 0 && (
          <div className="mt-2.5">
            <EvolutionDiffView
              skillName={suggestion.element_name}
              edits={suggestion.edits}
              originalContent={originalContent ?? undefined}
            />
          </div>
        )}
      </div>

      {/* Why this helps */}
      <div className="px-5 py-3 border-t border-default">
        <button
          onClick={() => setRationaleExpanded(!rationaleExpanded)}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {rationaleExpanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
          <Lightbulb className="w-3.5 h-3.5 text-accent-teal" />
          <span className="text-sm font-semibold text-accent-teal">Why this helps</span>
        </button>
        {rationaleExpanded && (
          <BulletText text={suggestion.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>

      {/* What this covers */}
      {matchedPatterns.length > 0 && (
        <div className="px-5 py-3 border-t border-default">
          <button
            onClick={() => setPatternsExpanded(!patternsExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {patternsExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
            <Target className="w-3.5 h-3.5 text-accent-teal" />
            <span className="text-sm font-semibold text-accent-teal">What this covers</span>
            <span className="text-dimmed">({matchedPatterns.length})</span>
          </button>
          {patternsExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedPatterns.map((p, i) => (
                <div key={i} className="border-l-2 border-accent-teal-border pl-3 space-y-1.5">
                  <h6 className="text-sm font-semibold text-primary">{p.title}</h6>
                  <BulletText text={p.description} className="text-sm text-secondary leading-relaxed" />
                  <StepRefList refs={p.example_refs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {showPreview && mergedContent !== null && (
        <PreviewDialog
          skillName={suggestion.element_name}
          content={mergedContent}
          onContentChange={setMergedContent}
          onInstall={handleUpdate}
          onCancel={() => setShowPreview(false)}
          syncTargets={syncTargets}
          variant="update"
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}
