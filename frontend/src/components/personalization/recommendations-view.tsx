import {
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  ExternalLink,
  Lightbulb,
  Search,
  Star,
} from "lucide-react";
import { useCallback, useState } from "react";
import type {
  RankedRecommendationItem,
  SkillSourceInfo,
} from "../../types";
import { BulletText } from "../bullet-text";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { Tooltip } from "../tooltip";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import { ConfidenceBar, SectionHeader } from "./skill-shared";
import { SkillPreviewDialog } from "./skill-preview-dialog";

export function RecommendationSection({
  recommendations,
  fetchWithToken,
  agentSources,
}: {
  recommendations: RankedRecommendationItem[];
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
            key={rec.item.item_id}
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
  rec: RankedRecommendationItem;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  agentSources: SkillSourceInfo[];
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [rationaleExpanded, setRationaleExpanded] = useState(false);

  const confidence = rec.scores.composite ?? rec.scores.relevance ?? 0;

  const handlePreview = useCallback(async () => {
    setShowPreview(true);
    if (previewContent !== null) return;
    setLoadingPreview(true);
    try {
      const res = await fetchWithToken(`/api/extensions/${rec.item.item_id}/content`);
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
  }, [fetchWithToken, rec.item.item_id, previewContent]);

  const handleInstall = useCallback(async (content: string, targets: string[]) => {
    try {
      const res = await fetchWithToken("/api/skills/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: rec.item.name, content }),
      });
      if (!res.ok) return;

      if (targets.length > 0) {
        await fetchWithToken(`/api/skills/sync/${rec.item.name}`, {
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
  }, [fetchWithToken, rec.item.name]);

  return (
    <div className="border border-default rounded-xl bg-control/20 overflow-hidden">
      {/* Header: Name + Confidence + Action */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="font-mono text-base font-bold text-primary">{rec.item.name}</span>
            {confidence > 0 && <ConfidenceBar confidence={confidence} accentColor="teal" />}
            {rec.item.stars > 0 && (
              <Tooltip text={`${rec.item.stars.toLocaleString()} stars`}>
                <span className="inline-flex items-center gap-0.5 text-[10px] text-dimmed cursor-help">
                  <Star className="w-2.5 h-2.5" /> {rec.item.stars.toLocaleString()}
                </span>
              </Tooltip>
            )}
            {rec.item.source_url && (
              <a
                href={rec.item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-dimmed hover:text-secondary transition"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
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
        <p className="text-sm text-secondary leading-relaxed mt-1.5">
          <span className="text-xs text-dimmed">{rec.item.repo_name}</span>
        </p>
      </div>

      {/* Why this helps */}
      <div className="px-5 py-3 border-t border-default/20">
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

      {showPreview && (
        <SkillPreviewDialog
          skillName={rec.item.name}
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
