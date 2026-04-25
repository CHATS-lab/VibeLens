// frontend/src/api/extensions.ts
import type {
  ExtensionDetail,
  ExtensionFileResponse,
  ExtensionListResponse,
  ExtensionMetaResponse,
  ExtensionSyncTarget,
  ExtensionTreeResponse,
} from "../types";

type FetchFn = (url: string, init?: RequestInit) => Promise<Response>;
const BASE = "/api/extensions";

export type LinkType = "symlink" | "copy";
const DEFAULT_LINK_TYPE: LinkType = "symlink";

export interface CollectionItemRef {
  extension_type: "skill" | "command" | "subagent" | "hook" | "plugin";
  name: string;
  pinned_version?: string | null;
}

export interface Collection {
  name: string;
  description: string;
  items: CollectionItemRef[];
  tags: string[];
  created_at: string;
  updated_at: string;
}

interface CollectionsApi {
  list(): Promise<{ items: Collection[]; total: number }>;
  get(name: string): Promise<Collection>;
  create(req: {
    name: string;
    description: string;
    items: CollectionItemRef[];
    tags: string[];
  }): Promise<Collection>;
  update(
    name: string,
    req: {
      description?: string;
      items?: CollectionItemRef[];
      tags?: string[];
    },
  ): Promise<Collection>;
  delete(name: string): Promise<{ deleted: string }>;
  install(
    name: string,
    agents: string[],
    linkType?: LinkType,
  ): Promise<{ name: string; results: Record<string, Record<string, string>> }>;
  export(name: string): Promise<Record<string, unknown>>;
  import(payload: Record<string, unknown>): Promise<Collection>;
}

interface CatalogApi {
  list(params: {
    page?: number;
    perPage?: number;
    sort?: string;
    search?: string;
    extensionType?: string;
  }): Promise<ExtensionListResponse>;
  getMeta(): Promise<ExtensionMetaResponse>;
  getItem(id: string): Promise<ExtensionDetail>;
  getContent(id: string): Promise<{ content: string; source: string }>;
  getTree(id: string): Promise<ExtensionTreeResponse>;
  getFile(id: string, path: string): Promise<ExtensionFileResponse>;
  install(
    id: string,
    targets: string[],
    overwrite?: boolean,
  ): Promise<{
    success: boolean;
    installed_path: string;
    message: string;
    results: Record<string, { success: boolean; message: string }>;
  }>;
}

interface TypeApi<T> {
  list(params?: {
    page?: number;
    pageSize?: number;
    search?: string;
    refresh?: boolean;
  }): Promise<{
    items: T[];
    total: number;
    page: number;
    page_size: number;
    sync_targets: ExtensionSyncTarget[];
  }>;
  get(name: string): Promise<{
    item: Record<string, unknown>;
    content: string;
    path: string;
  }>;
  getTree(name: string): Promise<ExtensionTreeResponse>;
  getFile(name: string, path: string): Promise<ExtensionFileResponse>;
  install(
    name: string,
    content: string,
    syncTo?: string[],
    linkType?: LinkType,
  ): Promise<T>;
  modify(name: string, content: string, linkType?: LinkType): Promise<T>;
  uninstall(name: string): Promise<{
    deleted: string;
    removed_from: string[];
  }>;
  syncToAgents(
    name: string,
    agents: string[],
    linkType?: LinkType,
  ): Promise<{ name: string; results: Record<string, boolean> }>;
  unsyncFromAgent(
    name: string,
    agent: string,
  ): Promise<{ name: string; agent: string }>;
  importFromAgent(
    agent: string,
  ): Promise<{ agent: string; imported: string[]; count: number }>;
}

interface SyncTargetsCache {
  get(): Promise<Record<string, ExtensionSyncTarget[]>>;
  invalidate(): void;
}

export type AgentCapability = {
  key: string;
  installed: boolean;
  supported_types: string[];
};

export type AgentCapabilitiesResponse = {
  agents: AgentCapability[];
};

interface AgentsApi {
  list(): Promise<AgentCapabilitiesResponse>;
}

export interface ExtensionsClient {
  catalog: CatalogApi;
  skills: TypeApi<unknown>;
  commands: TypeApi<unknown>;
  hooks: TypeApi<unknown>;
  subagents: TypeApi<unknown>;
  plugins: TypeApi<unknown>;
  agents: AgentsApi;
  collections: CollectionsApi;
  syncTargets: SyncTargetsCache;
}

export type TypeApiKey = "skills" | "commands" | "hooks" | "subagents" | "plugins";

/** Get the per-type API surface (skills/subagents/commands/hooks/plugins). */
export function typeApi(client: ExtensionsClient, key: TypeApiKey): TypeApi<unknown> {
  return client[key];
}

function createTypeApi<T>(fetchFn: FetchFn, typePlural: string): TypeApi<T> {
  const base = `${BASE}/${typePlural}`;
  const json = { "Content-Type": "application/json" };

  return {
    async list(params = {}) {
      const qs = new URLSearchParams();
      if (params.page) qs.set("page", String(params.page));
      if (params.pageSize) qs.set("page_size", String(params.pageSize));
      if (params.search) qs.set("search", params.search);
      if (params.refresh) qs.set("refresh", "true");
      const res = await fetchFn(`${base}?${qs}`);
      if (!res.ok) throw new Error(`Failed to list ${typePlural}`);
      return res.json();
    },
    async get(name) {
      const res = await fetchFn(`${base}/${encodeURIComponent(name)}`);
      if (!res.ok) throw new Error(`${typePlural} ${name} not found`);
      return res.json();
    },
    async getTree(name) {
      const res = await fetchFn(`${base}/${encodeURIComponent(name)}/tree`);
      if (!res.ok) throw new Error(`${typePlural} ${name} tree not available`);
      return res.json();
    },
    async getFile(name, path) {
      // Path segments must be individually encoded to preserve slashes.
      const encodedPath = path.split("/").map(encodeURIComponent).join("/");
      const res = await fetchFn(
        `${base}/${encodeURIComponent(name)}/files/${encodedPath}`,
      );
      if (!res.ok) throw new Error(`${typePlural} ${name} file not found`);
      return res.json();
    },
    async install(name, content, syncTo, linkType = DEFAULT_LINK_TYPE) {
      const res = await fetchFn(base, {
        method: "POST",
        headers: json,
        body: JSON.stringify({
          name,
          content,
          sync_to: syncTo || [],
          link_type: linkType,
        }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || `Failed to install ${name}`);
      }
      return res.json();
    },
    async modify(name, content, linkType = DEFAULT_LINK_TYPE) {
      const res = await fetchFn(
        `${base}/${encodeURIComponent(name)}`,
        {
          method: "PUT",
          headers: json,
          body: JSON.stringify({ content, link_type: linkType }),
        },
      );
      if (!res.ok) throw new Error(`Failed to modify ${name}`);
      return res.json();
    },
    async uninstall(name) {
      const res = await fetchFn(
        `${base}/${encodeURIComponent(name)}`,
        { method: "DELETE" },
      );
      if (!res.ok) throw new Error(`Failed to uninstall ${name}`);
      return res.json();
    },
    async syncToAgents(name, agents, linkType = DEFAULT_LINK_TYPE) {
      const res = await fetchFn(
        `${base}/${encodeURIComponent(name)}/agents`,
        {
          method: "POST",
          headers: json,
          body: JSON.stringify({ agents, link_type: linkType }),
        },
      );
      if (!res.ok) throw new Error(`Failed to sync ${name}`);
      return res.json();
    },
    async unsyncFromAgent(name, agent) {
      const res = await fetchFn(
        `${base}/${encodeURIComponent(name)}/agents/${encodeURIComponent(agent)}`,
        { method: "DELETE" },
      );
      if (!res.ok)
        throw new Error(`Failed to unsync ${name} from ${agent}`);
      return res.json();
    },
    async importFromAgent(agent) {
      const res = await fetchFn(
        `${base}/import/${encodeURIComponent(agent)}`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error(`Failed to import from ${agent}`);
      return res.json();
    },
  };
}

export function createExtensionsClient(
  fetchFn: FetchFn,
): ExtensionsClient {
  let cachedTargets: Record<string, ExtensionSyncTarget[]> | null = null;
  let cachePromise: Promise<
    Record<string, ExtensionSyncTarget[]>
  > | null = null;

  const syncTargets: SyncTargetsCache = {
    async get() {
      if (cachedTargets) return cachedTargets;
      if (cachePromise) return cachePromise;
      cachePromise = (async () => {
        const types = [
          "skills",
          "commands",
          "hooks",
          "subagents",
        ] as const;
        const results: Record<string, ExtensionSyncTarget[]> = {};
        await Promise.all(
          types.map(async (type) => {
            try {
              const res = await fetchFn(`${BASE}/${type}?page_size=1`);
              if (res.ok) {
                const data = await res.json();
                results[type.replace(/s$/, "")] = (
                  data.sync_targets || []
                ).map((t: ExtensionSyncTarget) => ({
                  agent: t.agent,
                  count: t.count,
                  dir: t.dir,
                }));
              }
            } catch {
              results[type.replace(/s$/, "")] = [];
            }
          }),
        );
        cachedTargets = results;
        cachePromise = null;
        return results;
      })();
      return cachePromise;
    },
    invalidate() {
      cachedTargets = null;
      cachePromise = null;
    },
  };

  const catalog: CatalogApi = {
    async list(params) {
      const qs = new URLSearchParams();
      if (params.page) qs.set("page", String(params.page));
      if (params.perPage)
        qs.set("per_page", String(params.perPage));
      if (params.sort) qs.set("sort", params.sort);
      if (params.search) qs.set("search", params.search);
      if (params.extensionType)
        qs.set("extension_type", params.extensionType);
      const res = await fetchFn(`${BASE}/catalog?${qs}`);
      if (!res.ok) throw new Error("Failed to list catalog");
      return res.json();
    },
    async getMeta() {
      const res = await fetchFn(`${BASE}/catalog/meta`);
      if (!res.ok) throw new Error("Failed to get catalog meta");
      return res.json();
    },
    async getItem(id) {
      const res = await fetchFn(`${BASE}/catalog/${id}`);
      if (!res.ok)
        throw new Error(`Catalog item ${id} not found`);
      return res.json();
    },
    async getContent(id) {
      const res = await fetchFn(`${BASE}/catalog/${id}/content`);
      if (!res.ok)
        throw new Error(`Content for ${id} not found`);
      return res.json();
    },
    async getTree(id) {
      const res = await fetchFn(`${BASE}/catalog/${id}/tree`);
      if (!res.ok) throw new Error(`Tree for ${id} not found`);
      return res.json();
    },
    async getFile(id, path) {
      const encodedPath = path.split("/").map(encodeURIComponent).join("/");
      const res = await fetchFn(
        `${BASE}/catalog/${id}/files/${encodedPath}`,
      );
      if (!res.ok) throw new Error(`File ${path} for ${id} not found`);
      return res.json();
    },
    async install(id, targets, overwrite = false) {
      const res = await fetchFn(
        `${BASE}/catalog/${id}/install`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_platforms: targets,
            overwrite,
          }),
        },
      );
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || "Install failed");
      }
      const data = await res.json();
      if (!data.success) {
        const results = (data.results ?? {}) as Record<string, { success: boolean; message?: string }>;
        const msgs = Object.entries(results)
          .filter(([, r]) => !r.success)
          .map(([k, r]) => `${k}: ${r.message || "failed"}`)
          .join("; ");
        throw new Error(msgs || data.message || "Install failed");
      }
      return data;
    },
  };

  const agents: AgentsApi = {
    async list() {
      const res = await fetchFn(`${BASE}/agents`);
      if (!res.ok) throw new Error("Failed to fetch agents");
      return res.json();
    },
  };

  const collectionsBase = `${BASE}/collections`;
  const jsonHeaders = { "Content-Type": "application/json" };
  const collections: CollectionsApi = {
    async list() {
      const res = await fetchFn(collectionsBase);
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    async get(name) {
      const res = await fetchFn(`${collectionsBase}/${encodeURIComponent(name)}`);
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    async create(req) {
      const res = await fetchFn(collectionsBase, {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    async update(name, req) {
      const res = await fetchFn(`${collectionsBase}/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: jsonHeaders,
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    async delete(name) {
      const res = await fetchFn(`${collectionsBase}/${encodeURIComponent(name)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    async install(name, agentList, linkType = DEFAULT_LINK_TYPE) {
      const res = await fetchFn(`${collectionsBase}/${encodeURIComponent(name)}/install`, {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ agents: agentList, link_type: linkType }),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    async export(name) {
      const res = await fetchFn(`${collectionsBase}/${encodeURIComponent(name)}/export`);
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    async import(payload) {
      const res = await fetchFn(`${collectionsBase}/import`, {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ payload }),
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
  };

  return {
    catalog,
    skills: createTypeApi(fetchFn, "skills"),
    commands: createTypeApi(fetchFn, "commands"),
    hooks: createTypeApi(fetchFn, "hooks"),
    subagents: createTypeApi(fetchFn, "subagents"),
    plugins: createTypeApi(fetchFn, "plugins"),
    agents,
    collections,
    syncTargets,
  };
}
