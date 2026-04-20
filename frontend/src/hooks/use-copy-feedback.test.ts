import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCopyFeedback } from "./use-copy-feedback";

describe("useCopyFeedback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(async () => undefined) },
    });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts idle", () => {
    const { result } = renderHook(() => useCopyFeedback());
    expect(result.current.state).toBe("idle");
    expect(result.current.copied).toBe(false);
  });

  it("transitions to copied after a successful copy, then back to idle", async () => {
    const { result } = renderHook(() => useCopyFeedback());
    await act(async () => {
      await result.current.copy("hello");
    });
    expect(result.current.copied).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.state).toBe("idle");
  });

  it("reports failed when the clipboard rejects and no fallback works", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(async () => { throw new Error("denied"); }) },
    });
    // Force the textarea fallback path to also fail.
    const origExec = document.execCommand;
    document.execCommand = vi.fn(() => false) as never;

    const { result } = renderHook(() => useCopyFeedback());
    await act(async () => {
      await result.current.copy("x");
    });
    expect(result.current.failed).toBe(true);

    document.execCommand = origExec;
  });
});
