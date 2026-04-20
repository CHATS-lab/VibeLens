import { describe, expect, it, vi } from "vitest";
import { dashboardClient } from "./dashboard";

describe("dashboardClient", () => {
  it("stats without filters uses the unfiltered URL", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ totals: {} }) }));
    const api = dashboardClient(fetchSpy as never);
    await api.stats();
    expect(fetchSpy).toHaveBeenCalledWith("/api/analysis/dashboard");
  });

  it("stats includes project_path and agent_name when filters are set", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ totals: {} }) }));
    const api = dashboardClient(fetchSpy as never);
    await api.stats({ project: "/home/me/repo", agent: "claude" });
    const calledUrl = String((fetchSpy.mock.calls[0] as unknown as [string])[0]);
    expect(calledUrl).toContain("project_path=%2Fhome%2Fme%2Frepo");
    expect(calledUrl).toContain("agent_name=claude");
  });

  it("stats appends refresh=true when opts.refresh is set", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ totals: {} }) }));
    const api = dashboardClient(fetchSpy as never);
    await api.stats(undefined, { refresh: true });
    expect(fetchSpy).toHaveBeenCalledWith("/api/analysis/dashboard?refresh=true");
  });

  it("toolUsage returns [] on non-OK", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 503 }));
    const api = dashboardClient(fetchSpy as never);
    expect(await api.toolUsage()).toEqual([]);
  });

  it("warmingStatus returns null on non-OK", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 404 }));
    const api = dashboardClient(fetchSpy as never);
    expect(await api.warmingStatus()).toBeNull();
  });

  it("export includes format and filter params", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob(["x"]),
    }));
    const api = dashboardClient(fetchSpy as never);
    await api.export("csv", { project: "/p", agent: "a" });
    const calledUrl = String((fetchSpy.mock.calls[0] as unknown as [string])[0]);
    expect(calledUrl).toContain("format=csv");
    expect(calledUrl).toContain("project_path=%2Fp");
    expect(calledUrl).toContain("agent_name=a");
  });
});
