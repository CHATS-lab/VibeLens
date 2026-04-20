import { describe, expect, it, vi } from "vitest";
import { analysisClient } from "./analysis";

describe("analysisClient", () => {
  it("POSTs /estimate with JSON body", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ total_cost_usd: 1.25 }),
    }));
    const api = analysisClient(fetchSpy as never, "/api/analysis/friction");
    const result = await api.estimate({ session_ids: ["a", "b"] });

    expect(result).toEqual({ total_cost_usd: 1.25 });
    expect(fetchSpy).toHaveBeenCalledWith("/api/analysis/friction/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_ids: ["a", "b"] }),
    });
  });

  it("throws the server's detail field on non-OK", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: false,
      status: 400,
      json: async () => ({ detail: "bad session id" }),
    }));
    const api = analysisClient(fetchSpy as never, "/api/analysis/friction");
    await expect(api.submit({ session_ids: [] })).rejects.toThrow("bad session id");
  });

  it("falls back to 'HTTP <status>' when the body has no detail", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({}),
    }));
    const api = analysisClient(fetchSpy as never, "/api/analysis/friction");
    await expect(api.submit({})).rejects.toThrow("HTTP 500");
  });

  it("load parses the response as the caller's type", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ id: "abc", type: "friction" }),
    }));
    const api = analysisClient(fetchSpy as never, "/api/x");
    const result = await api.load<{ id: string; type: string }>("abc");
    expect(result.id).toBe("abc");
    expect(fetchSpy).toHaveBeenCalledWith("/api/x/abc");
  });

  it("remove sends DELETE and throws on non-OK", async () => {
    const ok = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    const apiOk = analysisClient(ok as never, "/api/x");
    await apiOk.remove("id1");
    expect(ok).toHaveBeenCalledWith("/api/x/id1", { method: "DELETE" });

    const fail = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }));
    const apiFail = analysisClient(fail as never, "/api/x");
    await expect(apiFail.remove("missing")).rejects.toThrow("HTTP 404");
  });

  it("cancelJob POSTs the cancel endpoint", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    const api = analysisClient(fetchSpy as never, "/api/x");
    await api.cancelJob("job-1");
    expect(fetchSpy).toHaveBeenCalledWith("/api/x/jobs/job-1/cancel", { method: "POST" });
  });
});
