import { describe, it, expect } from "vitest";
import { DEFAULT_AGENT, DEFAULT_OS, OS_OPTIONS } from "./upload-constants";

describe("upload-constants", () => {
  it("DEFAULT_AGENT is a known string", () => {
    expect(typeof DEFAULT_AGENT).toBe("string");
    expect(DEFAULT_AGENT.length).toBeGreaterThan(0);
  });

  it("DEFAULT_OS is one of the OS_OPTIONS platforms", () => {
    const platforms = OS_OPTIONS.map((o) => o.platform);
    expect(platforms).toContain(DEFAULT_OS);
  });
});
