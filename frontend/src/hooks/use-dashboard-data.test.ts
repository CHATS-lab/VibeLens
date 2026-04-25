import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDashboardData, type DashboardCache } from "./use-dashboard-data";

const fetchSpy = vi.fn();

vi.mock("../app", () => ({
  useAppContext: () => ({ fetchWithToken: fetchSpy }),
}));

function mockStats() {
  return {
    ok: true,
    json: async () => ({ totals: { sessions: 10 }, project_distribution: {}, agent_distribution: {} }),
  };
}

function mockToolUsage(data: unknown[] = []) {
  return { ok: true, json: async () => data };
}

beforeEach(() => {
  fetchSpy.mockReset();
});

describe("useDashboardData", () => {
  it("skips the fallback fetch when a cache is supplied", async () => {
    const cache: DashboardCache = {
      stats: { totals: { sessions: 1 } } as never,
      toolUsage: [{ name: "bash", count: 3 }] as never,
    };

    const { result } = renderHook(() =>
      useDashboardData({ cache, selectedProject: null, selectedAgent: null }),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.stats).toBe(cache.stats);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("falls back to the stats endpoint when no cache is supplied", async () => {
    fetchSpy
      .mockImplementationOnce(async () => mockStats())
      .mockImplementationOnce(async () => mockToolUsage());

    const { result } = renderHook(() =>
      useDashboardData({ cache: null, selectedProject: null, selectedAgent: null }),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.stats).not.toBeNull();
    expect(fetchSpy.mock.calls[0]![0]).toBe("/api/dashboard");
  });

  it("refetches with filters when a project filter is set", async () => {
    const cache: DashboardCache = {
      stats: { totals: { sessions: 1 } } as never,
      toolUsage: [],
    };

    fetchSpy
      .mockImplementationOnce(async () => mockStats())
      .mockImplementationOnce(async () => mockToolUsage());

    const { rerender } = renderHook(
      ({ project }: { project: string | null }) =>
        useDashboardData({ cache, selectedProject: project, selectedAgent: null }),
      { initialProps: { project: null as string | null } },
    );
    rerender({ project: "/path" });

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    const urls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toContain("project_path=%2Fpath");
    expect(urls[1]).toContain("project_path=%2Fpath");
  });

  it("refresh re-scans sessions and refetches with refresh=true", async () => {
    const cache: DashboardCache = {
      stats: { totals: {} } as never,
      toolUsage: [],
    };
    fetchSpy
      .mockImplementationOnce(async () => ({ ok: true, json: async () => ({}) })) // refreshSessions
      .mockImplementationOnce(async () => mockStats()) // stats with refresh
      .mockImplementationOnce(async () => mockToolUsage());

    const { result } = renderHook(() =>
      useDashboardData({ cache, selectedProject: null, selectedAgent: null }),
    );

    await act(async () => {
      await result.current.refresh();
    });

    const urls = fetchSpy.mock.calls.map((c) => String(c[0]));
    expect(urls[0]).toBe("/api/sessions?refresh=true");
    expect(urls[1]).toContain("refresh=true");
  });

  it("restoreFromCache resets stats and toolUsage from the cached values", async () => {
    const cache: DashboardCache = {
      stats: { totals: { sessions: 5 } } as never,
      toolUsage: [{ name: "bash", count: 7 }] as never,
    };

    const { result } = renderHook(() =>
      useDashboardData({ cache, selectedProject: null, selectedAgent: null }),
    );

    await waitFor(() => expect(result.current.stats).toBe(cache.stats));
    act(() => result.current.restoreFromCache());
    expect(result.current.stats).toBe(cache.stats);
    expect(result.current.toolUsage).toBe(cache.toolUsage);
  });
});
