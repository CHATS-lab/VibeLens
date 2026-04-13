import { Check, ChevronDown, Compass, Filter, LayoutGrid, List, RefreshCw, Search, SlidersHorizontal, Tag } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import { TOGGLE_ACTIVE, TOGGLE_BUTTON_BASE, TOGGLE_CONTAINER, TOGGLE_INACTIVE } from "../../styles";
import type { CatalogItemSummary, CatalogListResponse, CatalogMetaResponse } from "../../types";
import { EmptyState } from "../empty-state";
import { ErrorBanner } from "../error-banner";
import { LoadingState } from "../loading-state";
import { CatalogCard } from "./catalog-card";
import { CATALOG_PAGE_SIZE, ITEM_TYPE_LABELS, SORT_OPTIONS, type CatalogViewMode } from "./catalog-constants";
import { CatalogDetailView } from "./catalog-detail-view";
import { CatalogPagination } from "./catalog-pagination";
import { NoResultsState } from "./skill-shared";

const SEARCH_DEBOUNCE_MS = 300;

interface FilterDropdownProps {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  icon: React.ReactNode;
  placeholder: string;
}

function FilterDropdown({ value, options, onChange, icon, placeholder }: FilterDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const activeLabel = options.find((o) => o.value === value)?.label ?? placeholder;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 bg-control text-secondary text-sm rounded px-2.5 py-1.5 border border-card hover:border-hover transition cursor-pointer"
      >
        {icon}
        <span className="truncate">{activeLabel}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-dimmed shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 min-w-full bg-control border border-card rounded-md shadow-xl overflow-hidden">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full flex items-center gap-2 px-2.5 py-1.5 text-sm transition ${
                value === opt.value
                  ? "bg-accent-cyan-subtle text-cyan-700 dark:text-cyan-200"
                  : "text-secondary hover:bg-control-hover hover:text-primary"
              }`}
            >
              {value === opt.value ? (
                <Check className="w-3.5 h-3.5 text-accent-cyan shrink-0" />
              ) : (
                <span className="w-3.5 shrink-0" />
              )}
              <span className="truncate">{opt.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function CatalogExploreTab() {
  const { fetchWithToken } = useAppContext();

  const [items, setItems] = useState<CatalogItemSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState("quality");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<CatalogViewMode>("list");
  const [categories, setCategories] = useState<string[]>([]);
  const [hasProfile, setHasProfile] = useState(false);
  const [page, setPage] = useState(1);

  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [detailItem, setDetailItem] = useState<CatalogItemSummary | null>(null);

  // Load catalog metadata once on mount
  useEffect(() => {
    fetchWithToken("/api/catalog/meta")
      .then((res) => res.json())
      .then((data: CatalogMetaResponse) => {
        setCategories(data.categories);
        setHasProfile(data.has_profile);
      })
      .catch(() => {});
  }, [fetchWithToken]);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const fetchCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        per_page: String(CATALOG_PAGE_SIZE),
        sort: sortBy,
      });
      if (debouncedSearch) params.set("search", debouncedSearch);
      if (typeFilter) params.set("item_type", typeFilter);
      if (categoryFilter) params.set("category", categoryFilter);

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
  }, [fetchWithToken, page, debouncedSearch, typeFilter, sortBy, categoryFilter]);

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

  const sortOptions = useMemo(
    () =>
      SORT_OPTIONS.filter((o) => !o.needsProfile || hasProfile).map((o) => ({
        value: o.value,
        label: o.label,
      })),
    [hasProfile],
  );

  const categoryOptions = useMemo(
    () => [
      { value: "", label: "All categories" },
      ...categories.map((c) => ({ value: c, label: c })),
    ],
    [categories],
  );

  const totalPages = Math.ceil(total / CATALOG_PAGE_SIZE);

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
            <p className="text-xs text-secondary">Browse tools, skills, hooks, and agents</p>
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
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search skills, agents, commands, hooks, MCPs..."
          className="w-full pl-10 pr-4 py-2.5 text-sm bg-panel border border-card rounded-lg text-primary placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-teal-500/30 focus:border-teal-600 transition"
        />
      </div>

      {/* Controls: sort dropdown, category dropdown, view mode toggle */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <FilterDropdown
          value={sortBy}
          options={sortOptions}
          onChange={(v) => { setSortBy(v); setPage(1); }}
          icon={<SlidersHorizontal className="w-3.5 h-3.5 text-muted shrink-0" />}
          placeholder="Sort"
        />
        {categoryOptions.length > 1 && (
          <FilterDropdown
            value={categoryFilter ?? ""}
            options={categoryOptions}
            onChange={(v) => { setCategoryFilter(v || null); setPage(1); }}
            icon={<Tag className="w-3.5 h-3.5 text-muted shrink-0" />}
            placeholder="All categories"
          />
        )}
        <div className="ml-auto">
          <div className={TOGGLE_CONTAINER}>
            <button
              onClick={() => setViewMode("list")}
              className={`${TOGGLE_BUTTON_BASE} px-2.5 ${viewMode === "list" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE}`}
            >
              <List className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode("card")}
              className={`${TOGGLE_BUTTON_BASE} px-2.5 ${viewMode === "card" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE}`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
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

      {/* States */}
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {loading && items.length === 0 && <LoadingState label="Loading catalog..." />}
      {!loading && !error && total === 0 && !searchQuery && !typeFilter && (
        <EmptyState icon={Compass} title="No catalog items" subtitle="Run the catalog builder to populate" />
      )}
      {!loading && total === 0 && (searchQuery || typeFilter) && <NoResultsState />}

      {/* Results */}
      {items.length > 0 && (
        <div>
          <div className="text-sm text-secondary mb-3">{total} items</div>
          <div className={viewMode === "card" ? "grid grid-cols-2 lg:grid-cols-3 gap-3" : "space-y-2"}>
            {items.map((item) => (
              <CatalogCard
                key={item.item_id}
                item={item}
                isInstalled={installedIds.has(item.item_id)}
                onInstalled={handleInstalled}
                onViewDetail={setDetailItem}
                viewMode={viewMode}
              />
            ))}
          </div>
        </div>
      )}

      <CatalogPagination page={page} totalPages={totalPages} onPageChange={setPage} />
    </div>
  );
}
