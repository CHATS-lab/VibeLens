import {
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  Lightbulb,
  Search,
  Target,
} from "lucide-react";
import { useCallback, useState } from "react";
import type {
  SkillRecommendation,
  SkillSourceInfo,
  WorkflowPattern,
} from "../../types";
import { BulletText } from "../bullet-text";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { Tooltip } from "../tooltip";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import { ConfidenceBar, SectionHeader } from "./skill-shared";
import { StepRefList } from "./skill-patterns-view";
import { SkillPreviewDialog } from "./skill-preview-dialog";

export function RecommendationSection({
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
