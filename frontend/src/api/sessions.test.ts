import { describe, expect, it, vi } from "vitest";
import { sessionsClient } from "./sessions";

describe("sessionsClient", () => {
  it("search URL-encodes the query and returns scored results", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => [
        { session_id: "a", score: 1.2 },
        { session_id: "b", score: 0.4 },
      ],
    }));
    const api = sessionsClient(fetchSpy as never);
    const hits = await api.search("hello world");
    expect(fetchSpy).toHaveBeenCalledWith("/api/sessions/search?q=hello+world");
    expect(hits).toEqual([
      { session_id: "a", score: 1.2 },
      { session_id: "b", score: 0.4 },
    ]);
  });

  it("flow uses share endpoint when shareToken is present", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ nodes: [] }) }));
    const api = sessionsClient(fetchSpy as never);
    await api.flow("sid", "tok-1");
    expect(fetchSpy).toHaveBeenCalledWith("/api/shares/tok-1/flow");
  });

  it("flow returns null when the endpoint is not OK", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 404 }));
    const api = sessionsClient(fetchSpy as never);
    const result = await api.flow("sid", null);
    expect(result).toBeNull();
  });

  it("stats returns null on non-OK", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 500 }));
    const api = sessionsClient(fetchSpy as never);
    expect(await api.stats("sid")).toBeNull();
  });

  it("createShare throws with the status code in the message", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) }));
    const api = sessionsClient(fetchSpy as never);
    await expect(api.createShare("sid")).rejects.toThrow("403");
  });

  it("listAllIds hits /api/sessions and maps session_id", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => [{ session_id: "a" }, { session_id: "b" }],
    }));
    const api = sessionsClient(fetchSpy as never);
    expect(await api.listAllIds()).toEqual(["a", "b"]);
    expect(fetchSpy).toHaveBeenCalledWith("/api/sessions");
  });
});
