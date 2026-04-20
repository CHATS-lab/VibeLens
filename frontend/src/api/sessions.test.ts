import { describe, expect, it, vi } from "vitest";
import { sessionsClient } from "./sessions";

describe("sessionsClient", () => {
  it("search URL-encodes query and sources", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => [] }));
    const api = sessionsClient(fetchSpy as never);
    await api.search("hello world", ["user_prompts", "session_id"]);
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/sessions/search?q=hello+world&sources=user_prompts%2Csession_id",
    );
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
});
