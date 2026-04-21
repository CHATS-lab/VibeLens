import { describe, expect, it, vi } from "vitest";
import { versionClient } from "./version";

describe("versionClient", () => {
  it("get calls /api/version and returns parsed JSON", async () => {
    const payload = {
      current: "1.0.4",
      latest: "1.0.5",
      update_available: true,
      is_dev_build: false,
      install_method: "uv",
      install_commands: {
        uv: "uv tool upgrade vibelens",
        pip: "pip install -U vibelens",
        npx: "npm install -g @chats-lab/vibelens@latest",
      },
    };
    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => payload }));
    const api = versionClient(fetchSpy as never);
    const result = await api.get();
    expect(fetchSpy).toHaveBeenCalledWith("/api/version");
    expect(result.latest).toBe("1.0.5");
    expect(result.install_commands.uv).toContain("uv tool upgrade");
  });

  it("get throws on non-OK", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 503 }));
    const api = versionClient(fetchSpy as never);
    await expect(api.get()).rejects.toThrow("HTTP 503");
  });
});
