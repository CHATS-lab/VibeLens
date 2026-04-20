import { describe, expect, it, vi } from "vitest";
import { llmClient } from "./llm";

describe("llmClient", () => {
  it("status returns the parsed body", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => ({ backend_id: "openai", model: "gpt-5" }),
    }));
    const api = llmClient(fetchSpy as never);
    const result = await api.status();
    expect(result.backend_id).toBe("openai");
    expect(fetchSpy).toHaveBeenCalledWith("/api/llm/status");
  });

  it("configure POSTs the payload and surfaces the detail error", async () => {
    const fail = vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({ detail: "api key required" }),
    }));
    const api = llmClient(fail as never);
    await expect(
      api.configure({ backend: "openai", api_key: "" }),
    ).rejects.toThrow("api key required");
  });

  it("litellmPresets unwraps { models: [...] }", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => ({ models: [{ name: "gpt-5" }, { name: "claude-opus-4-7" }] }),
    }));
    const api = llmClient(fetchSpy as never);
    const result = await api.litellmPresets();
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe("gpt-5");
  });

  it("litellmPresets returns [] when the body has no models field", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => ({}),
    }));
    const api = llmClient(fetchSpy as never);
    const result = await api.litellmPresets();
    expect(result).toEqual([]);
  });
});
