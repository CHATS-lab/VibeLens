import {
  AlertCircle,
  Check,
  Compass,
  Download,
  ExternalLink,
  Globe,
  Loader2,
  Plus,
  RefreshCw,
  Share2,
  Sparkles,
  Star,
  Tag,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { FeaturedSkill, FeaturedSkillsResponse, SkillInfo, SkillSourceInfo } from "../../types";
import { Tooltip } from "../tooltip";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "../modal";
import { CategoryBadge, TagList, TagPill } from "./skill-badges";
import { CATEGORY_COLORS, CATEGORY_LABELS, SOURCE_COLORS } from "./skill-constants";
import {
  EmptyState,
  ErrorBanner,
  LoadingState,
  NoResultsState,
  SkillCount,
  SkillSearchBar,
  SourceFilterBar,
} from "./skill-shared";

export function ExploreSkillsTab() {
  const { fetchWithToken } = useAppContext();
  const [featured, setFeatured] = useState<FeaturedSkill[]>([]);
  const [allSkills, setAllSkills] = useState<FeaturedSkill[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [detailSkill, setDetailSkill] = useState<FeaturedSkill | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [installedSlugs, setInstalledSlugs] = useState<Set<string>>(new Set());
  const [agentSources, setAgentSources] = useState<SkillSourceInfo[]>([]);

  const fetchFeatured = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [featuredRes, localRes, sourcesRes] = await Promise.all([
        fetchWithToken("/api/skills/featured"),
        fetchWithToken("/api/skills/local"),
        fetchWithToken("/api/skills/sources"),
      ]);
      if (!featuredRes.ok) throw new Error(`HTTP ${featuredRes.status}`);
      const data: FeaturedSkillsResponse = await featuredRes.json();
      setAllSkills(data.skills);
      setFeatured(data.skills);
      setCategories(data.categories);
      setUpdatedAt(data.updated_at);

      if (localRes.ok) {
        const localData = await localRes.json();
        const local: SkillInfo[] = localData.items ?? localData;
        setInstalledSlugs(new Set(local.map((s) => s.name)));
      }
      if (sourcesRes.ok) {
        setAgentSources(await sourcesRes.json());
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [fetchWithToken]);

  useEffect(() => {
    fetchFeatured();
  }, [fetchFeatured]);

  useEffect(() => {
    let result = allSkills;
    if (categoryFilter) {
      result = result.filter((s) => s.category === categoryFilter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.summary.toLowerCase().includes(q) ||
          s.tags.some((t) => t.toLowerCase().includes(q)),
      );
    }
    setFeatured(result);
  }, [allSkills, categoryFilter, searchQuery]);

  const handleInstalled = useCallback((slug: string) => {
    setInstalledSlugs((prev) => new Set([...prev, slug]));
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-teal-600/20">
            <Compass className="w-5 h-5 text-teal-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-zinc-100">Explore Skills</h2>
            <p className="text-xs text-zinc-500">
              {allSkills.length} community skills from the Anthropic registry
              {updatedAt && (
                <span className="ml-1 text-zinc-600">
                  · updated {new Date(updatedAt).toLocaleDateString()}
                </span>
              )}
            </p>
          </div>
        </div>
        <button
          onClick={fetchFeatured}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 rounded-md transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Personalization CTA banner */}
      <div className="relative mb-5 px-4 py-3.5 rounded-lg border border-teal-800/40 bg-gradient-to-r from-teal-950/40 via-teal-900/20 to-indigo-950/40 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(139,92,246,0.08),transparent_60%)]" />
        <div className="relative flex items-center gap-3">
          <div className="shrink-0 p-2 rounded-lg bg-teal-500/15 border border-teal-500/20">
            <Zap className="w-4 h-4 text-teal-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-teal-300">Not sure which skills to add?</p>
            <p className="text-xs text-teal-400/70 mt-0.5">
              Switch to the <span className="font-semibold text-teal-300">Retrieve</span> tab — it analyzes your coding sessions and recommends skills tailored to your workflow.
            </p>
          </div>
          <Sparkles className="w-5 h-5 text-teal-500/40 shrink-0" />
        </div>
      </div>

      {/* Category filter */}
      <SourceFilterBar
        items={categories}
        activeKey={categoryFilter}
        onSelect={setCategoryFilter}
        totalCount={allSkills.length}
        countByKey={(key) => allSkills.filter((s) => s.category === key).length}
        colorMap={CATEGORY_COLORS}
        labelMap={CATEGORY_LABELS}
      />

      <SkillSearchBar
        value={searchQuery}
        onChange={setSearchQuery}
        placeholder="Search community skills..."
        focusRingColor="focus:ring-teal-500/30 focus:border-teal-600"
      />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {loading && allSkills.length === 0 && <LoadingState label="Loading featured skills..." />}
      {!loading && !error && allSkills.length === 0 && (
        <EmptyState icon={Globe} title="No featured skills found" subtitle="featured-skills.json may be missing or empty" />
      )}
      {!loading && allSkills.length > 0 && featured.length === 0 && <NoResultsState />}

      {featured.length > 0 && (
        <div className="space-y-2">
          <SkillCount filtered={featured.length} total={allSkills.length} />
          {featured.map((skill) => (
            <FeaturedSkillCard
              key={skill.slug}
              skill={skill}
              isInstalled={installedSlugs.has(skill.slug)}
              onViewDetail={setDetailSkill}
            />
          ))}
        </div>
      )}

      {detailSkill && (
        <FeaturedSkillDetailPopup
          skill={detailSkill}
          isInstalled={installedSlugs.has(detailSkill.slug)}
          agentSources={agentSources}
          fetchWithToken={fetchWithToken}
          onInstalled={handleInstalled}
          onClose={() => setDetailSkill(null)}
        />
      )}
    </div>
  );
}

function FeaturedSkillCard({
  skill,
  isInstalled,
  onViewDetail,
}: {
  skill: FeaturedSkill;
  isInstalled: boolean;
  onViewDetail: (skill: FeaturedSkill) => void;
}) {
  return (
    <div className={`border rounded-lg transition ${
      isInstalled
        ? "border-emerald-800/40 bg-emerald-950/20 hover:bg-emerald-950/30"
        : "border-zinc-700/50 bg-zinc-800/50 hover:bg-zinc-800/80"
    }`}>
      <button
        onClick={() => onViewDetail(skill)}
        className="w-full text-left px-4 py-3 flex items-start gap-3 min-w-0"
      >
        <div className={`shrink-0 mt-0.5 p-1.5 rounded-md ${isInstalled ? "bg-emerald-600/20" : "bg-teal-600/20"}`}>
          {isInstalled ? <Check className="w-4 h-4 text-emerald-400" /> : <Globe className="w-4 h-4 text-teal-400" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-sm font-semibold text-zinc-100">{skill.name}</span>
            <CategoryBadge category={skill.category} />
            {skill.stars > 0 && (
              <Tooltip text={`${skill.stars.toLocaleString()} GitHub stars`}>
                <span className="flex items-center gap-0.5 text-[10px] text-amber-400/70">
                  <Star className="w-2.5 h-2.5" />
                  {skill.stars >= 1000 ? `${(skill.stars / 1000).toFixed(1)}k` : skill.stars}
                </span>
              </Tooltip>
            )}
            {isInstalled && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-700/30 font-medium">
                Installed
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-400 mt-1 line-clamp-2">{skill.summary}</p>
          <TagList tags={skill.tags} />
        </div>
        <div className="shrink-0 mt-1">
          <ExternalLink className="w-3.5 h-3.5 text-zinc-600" />
        </div>
      </button>
    </div>
  );
}

function FeaturedSkillDetailPopup({
  skill,
  isInstalled,
  agentSources,
  fetchWithToken,
  onInstalled,
  onClose,
}: {
  skill: FeaturedSkill;
  isInstalled: boolean;
  agentSources: SkillSourceInfo[];
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onInstalled: (slug: string) => void;
  onClose: () => void;
}) {
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(isInstalled);
  const [installError, setInstallError] = useState<string | null>(null);
  const [selectedTargets, setSelectedTargets] = useState<Set<string>>(new Set());

  const toggleTarget = useCallback((key: string) => {
    setSelectedTargets((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setInstallError(null);
    try {
      const res = await fetchWithToken("/api/skills/featured/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: skill.slug, targets: [...selectedTargets] }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setInstalled(true);
      onInstalled(skill.slug);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstalling(false);
    }
  }, [fetchWithToken, skill.slug, selectedTargets, onInstalled]);

  return (
    <Modal onClose={onClose}>
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <div className={`p-1.5 rounded-md ${installed ? "bg-emerald-600/20" : "bg-teal-600/20"}`}>
            {installed ? <Check className="w-4 h-4 text-emerald-400" /> : <Globe className="w-4 h-4 text-teal-400" />}
          </div>
          <div>
            <h2 className="text-sm font-semibold font-mono text-zinc-100">{skill.name}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <CategoryBadge category={skill.category} />
              {skill.stars > 0 && (
                <span className="flex items-center gap-0.5 text-[10px] text-amber-400/70">
                  <Star className="w-2.5 h-2.5" /> {skill.stars.toLocaleString()}
                </span>
              )}
              {installed && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-700/30 font-medium">
                  Installed
                </span>
              )}
            </div>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        <p className="text-sm text-zinc-300 leading-relaxed">{skill.summary}</p>

        {skill.tags.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-2">
              <Tag className="w-3 h-3" /> <span>Tags</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {skill.tags.map((tag) => <TagPill key={tag} tag={tag} />)}
            </div>
          </div>
        )}

        <div className="flex items-center gap-6 text-xs text-zinc-400">
          {skill.stars > 0 && (
            <div className="flex items-center gap-1.5">
              <Star className="w-3.5 h-3.5 text-amber-400" />
              <span>{skill.stars.toLocaleString()} stars</span>
            </div>
          )}
          {skill.downloads > 0 && (
            <div className="flex items-center gap-1.5">
              <Download className="w-3.5 h-3.5 text-zinc-500" />
              <span>{skill.downloads.toLocaleString()} downloads</span>
            </div>
          )}
          <span className="text-zinc-500">Updated {new Date(skill.updated_at).toLocaleDateString()}</span>
        </div>

        {!installed && agentSources.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-2">
              <Share2 className="w-3 h-3" /> <span>Also install to agent interfaces</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {agentSources.map((src) => (
                <button
                  key={src.key}
                  onClick={() => toggleTarget(src.key)}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium rounded-md border transition ${
                    selectedTargets.has(src.key)
                      ? SOURCE_COLORS[src.key] || "bg-zinc-700 text-zinc-300 border-zinc-600"
                      : "text-zinc-500 border-zinc-700/50 hover:text-zinc-300 hover:border-zinc-600"
                  }`}
                >
                  {selectedTargets.has(src.key) ? <Check className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
                  {src.label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-zinc-600 mt-1.5">
              Skills are always installed to the central store (~/.vibelens/skills/)
            </p>
          </div>
        )}

        {installError && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-900/20 border border-red-800/30">
            <AlertCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 shrink-0" />
            <p className="text-xs text-red-300">{installError}</p>
          </div>
        )}

        {skill.source_url && (
          <div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 mb-2">
              <ExternalLink className="w-3 h-3" /> <span>Source</span>
            </div>
            <a
              href={skill.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-teal-400 hover:text-teal-300 underline underline-offset-2 transition"
            >
              {skill.source_url} <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        )}
      </ModalBody>

      <ModalFooter>
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition"
        >
          Close
        </button>
        {skill.source_url && (
          <a
            href={skill.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-300 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded transition"
          >
            <ExternalLink className="w-3.5 h-3.5" /> GitHub
          </a>
        )}
        {!installed ? (
          <button
            onClick={handleInstall}
            disabled={installing}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium text-white bg-teal-600 hover:bg-teal-500 rounded transition disabled:opacity-50"
          >
            {installing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            {installing ? "Installing..." : "Install Skill"}
          </button>
        ) : (
          <span className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium text-emerald-400 bg-emerald-900/20 border border-emerald-700/30 rounded">
            <Check className="w-3.5 h-3.5" /> Installed
          </span>
        )}
      </ModalFooter>
    </Modal>
  );
}
