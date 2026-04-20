import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useResetOnKey } from "./use-reset-on-key";

describe("useResetOnKey", () => {
  it("does not run on initial mount when key is 0", () => {
    const reset = vi.fn();
    renderHook(({ k }) => useResetOnKey(k, reset), { initialProps: { k: 0 } });
    expect(reset).not.toHaveBeenCalled();
  });

  it("runs when the key bumps above 0", () => {
    const reset = vi.fn();
    const { rerender } = renderHook(
      ({ k }: { k: number }) => useResetOnKey(k, reset),
      { initialProps: { k: 0 } },
    );
    rerender({ k: 1 });
    expect(reset).toHaveBeenCalledTimes(1);
    rerender({ k: 2 });
    expect(reset).toHaveBeenCalledTimes(2);
  });
});
