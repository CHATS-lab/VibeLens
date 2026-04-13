import { Compass, Filter, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import type { CatalogItemSummary, CatalogListResponse } from "../../types";
import { EmptyState } from "../empty-state";
import { ErrorBanner } from "../error-banner";
import { LoadingState } from "../loading-state";
import { NoResultsState, SkillCount } from "./skill-shared";
import { CatalogCard } from "./catalog-card";
import { CatalogDetailView } from "./catalog-detail-view";
import { CATALOG_PAGE_SIZE, ITEM_TYPE_LABELS } from "./catalog-constants";

const SEARCH_DEBOUNCE_MS = 300;

export function CatalogExploreTab() {
  const { fetchWithToken } = useAppContext();

  const [items, setItems] = useState<CatalogItemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // Installed tracking
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());

  // Detail view — when set, replaces the entire list with a detail page
  const [detailItem, setDetailItem] = useState<CatalogItemSummary | null>(null);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Fetch catalog
  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(CATALOG_PAGE_SIZE),
        sort: "quality",
      });
      if (debouncedSearch) params.set("search", debouncedSearch);
      if (typeFilter) params.set("item_type", typeFilter);

      const res = await fetchWithToken(`/api/catalog?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: CatalogListResponse = await res.json();
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [fetchWithToken, page, debouncedSearch, typeFilter]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const handleInstalled = useCallback((itemId: string) => {
    setInstalledIds((prev) => new Set([...prev, itemId]));
  }, []);

  const typeOptions = useMemo(
    () => Object.entries(ITEM_TYPE_LABELS).map(([key, label]) => ({ key, label })),
    [],
  );

  const totalPages = Math.ceil(total / CATALOG_PAGE_SIZE);

  // --- Detail page view (replaces list) ---
  if (detailItem) {
    return (
      <CatalogDetailView
        item={detailItem}
        isInstalled={installedIds.has(detailItem.item_id)}
        onBack={() => setDetailItem(null)}
        onInstalled={handleInstalled}
      />
    );
  }

  // --- List view ---
  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-accent-teal-subtle">
            <Compass className="w-5 h-5 text-accent-teal" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-primary">Explore Catalog</h2>
            <p className="text-xs text-secondary">
              {total} tools and skills for your coding agent
            </p>
          </div>
        </div>
        <button
          onClick={fetchCatalog}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-muted hover:text-secondary bg-control hover:bg-control-hover border border-card rounded-md transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search skills, agents, commands, hooks, MCPs..."
          className="w-full pl-10 pr-4 py-2.5 text-sm bg-panel border border-card rounded-lg text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-teal-500/30 focus:border-teal-600 transition"
        />
      </div>

      {/* Type filter pills */}
      <div className="flex items-center gap-1.5 mb-4 flex-wrap">
        <Filter className="w-3.5 h-3.5 text-muted mr-1" />
        <button
          onClick={() => { setTypeFilter(null); setPage(1); }}
          className={`px-2.5 py-1 text-xs rounded-full transition ${
            !typeFilter
              ? "bg-teal-600 text-white dark:bg-teal-500"
              : "bg-control text-muted border border-card hover:text-secondary"
          }`}
        >
          All
        </button>
        {typeOptions.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => { setTypeFilter(typeFilter === key ? null : key); setPage(1); }}
            className={`px-2.5 py-1 text-xs rounded-full transition ${
              typeFilter === key
                ? "bg-teal-600 text-white dark:bg-teal-500"
                : "bg-control text-muted border border-card hover:text-secondary"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Error / Loading / Empty states */}
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {loading && items.length === 0 && <LoadingState label="Loading catalog..." />}
      {!loading && !error && total === 0 && !searchQuery && !typeFilter && (
        <EmptyState icon={Compass} title="No catalog items" subtitle="Run the catalog builder to populate" />
      )}
      {!loading && total === 0 && (searchQuery || typeFilter) && <NoResultsState />}

      {/* Results */}
      {items.length > 0 && (
        <div className="space-y-2">
          <SkillCount filtered={total} total={total} />
          {items.map((item) => (
            <CatalogCard
              key={item.item_id}
              item={item}
              isInstalled={installedIds.has(item.item_id)}
              onInstalled={handleInstalled}
              onViewDetail={setDetailItem}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-xs text-muted hover:text-secondary bg-control border border-card rounded transition disabled:opacity-30"
          >
            Previous
          </button>
          <span className="text-xs text-muted">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-xs text-muted hover:text-secondary bg-control border border-card rounded transition disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
