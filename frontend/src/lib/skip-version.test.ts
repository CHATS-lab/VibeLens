import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearSkippedVersion, getSkippedVersion, setSkippedVersion } from "./skip-version";

describe("skip-version", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("round-trips a value", () => {
    setSkippedVersion("1.0.5");
    expect(getSkippedVersion()).toBe("1.0.5");
  });

  it("clears", () => {
    setSkippedVersion("1.0.5");
    clearSkippedVersion();
    expect(getSkippedVersion()).toBeNull();
  });

  it("returns null when storage throws on read", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(getSkippedVersion()).toBeNull();
  });

  it("does not throw when storage rejects a write", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => setSkippedVersion("1.0.5")).not.toThrow();
  });
});
