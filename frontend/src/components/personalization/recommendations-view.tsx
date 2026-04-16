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
  Skill,
  SkillSyncTarget,
} from "../../types";
import { BulletText } from "../bullet-text";
import { InstallLocallyDialog } from "../install-locally-dialog";
import { Tooltip } from "../tooltip";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import { TagList } from "./badges";
import { ExtensionDetailPopup } from "./cards";
import { ConfidenceBar, SectionHeader } from "./shared";

export function RecommendationSection({
  recommendations,
  fetchWithToken,
  syncTargets,
}: {
  recommendations: RankedRecommendationItem[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  syncTargets: SkillSyncTarget[];
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
            key={rec.item.extension_id}
            rec={rec}
            fetchWithToken={fetchWithToken}
            syncTargets={syncTargets}
          />
        ))}
      </div>
    </section>
  );
}

function RecommendationCard({
  rec,
  fetchWithToken,
  syncTargets,
}: {
  rec: RankedRecommendationItem;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  syncTargets: SkillSyncTarget[];
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [showDetail, setShowDetail] = useState(false);
  const [detailContent, setDetailContent] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [installed, setInstalled] = useState(false);
  const [rationaleExpanded, setRationaleExpanded] = useState(false);

  const relevance = rec.scores.relevance ?? 0;
  const tags = rec.item.tags ?? [];

  const handleOpenDetail = useCallback(async () => {
    setShowDetail(true);
    if (detailContent !== null) return;
    setLoadingDetail(true);
    try {
      const res = await fetchWithToken(`/api/extensions/${rec.item.extension_id}/content`);
      if (res.ok) {
        const data = await res.json();
        setDetailContent(data.content);
      } else {
        setDetailContent("(Content unavailable)");
      }
    } catch {
      setDetailContent("(Failed to fetch content)");
    } finally {
      setLoadingDetail(false);
    }
  }, [fetchWithToken, rec.item.extension_id, detailContent]);

  const handleInstall = useCallback(
    async (content: string, targets: string[]) => {
      const res = await fetchWithToken("/api/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: rec.item.name, content, sync_to: targets }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setInstalled(true);
    },
    [fetchWithToken, rec.item.name],
  );

  // Virtual Skill shape for ExtensionDetailPopup reuse
  const virtualSkill: Skill = {
    name: rec.item.name,
    description: rec.item.description || "",
    tags,
    allowed_tools: [],
    content_hash: "",
    installed_in: [],
  };

  return (
    <div className="border border-default rounded-xl bg-control/20 overflow-hidden">
      {/* Header: Name + Relevance + Action */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0 flex-wrap">
            <span className="font-mono text-base font-bold text-primary">{rec.item.name}</span>
            {relevance > 0 && <ConfidenceBar confidence={relevance} accentColor="teal" />}
            {rec.item.stars > 0 && (
              <Tooltip text={`${rec.item.stars.toLocaleString()} stars`}>
                <span className="inline-flex items-center gap-0.5 text-[11px] text-amber-500 dark:text-amber-400 cursor-help">
                  <Star className="w-3 h-3 fill-amber-400 text-amber-400" /> {rec.item.stars.toLocaleString()}
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
          <div className="flex items-center gap-2.5 shrink-0">
            {installed ? (
              <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-teal bg-accent-teal-subtle rounded-lg border border-accent-teal">
                <Check className="w-3.5 h-3.5" /> Installed
              </span>
            ) : (
              <Tooltip text="View details and install">
                <button
                  onClick={() => guardAction(handleOpenDetail)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition"
                >
                  <Eye className="w-3.5 h-3.5" />
                  Preview &amp; Install
                </button>
              </Tooltip>
            )}
          </div>
        </div>
        {rec.item.description && (
          <p className="text-sm text-secondary leading-relaxed mt-2 line-clamp-3">
            {rec.item.description}
          </p>
        )}
        <p className="text-xs text-dimmed mt-1.5">{rec.item.repo_name}</p>
        {tags.length > 0 && <TagList tags={tags} />}
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
          <span className="text-sm font-semibold text-accent-teal">Why this helps</span>
        </button>
        {rationaleExpanded && (
          <BulletText text={rec.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>

      {showDetail && (
        <ExtensionDetailPopup
          skill={virtualSkill}
          syncTargets={syncTargets}
          onClose={() => setShowDetail(false)}
          fetchWithToken={fetchWithToken}
          onRefresh={() => {}}
          mode="install"
          previewContent={detailContent ?? ""}
          loadingContent={loadingDetail}
          stars={rec.item.stars}
          sourceUrl={rec.item.source_url}
          onInstall={handleInstall}
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}
