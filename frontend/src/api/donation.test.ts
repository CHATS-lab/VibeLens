import { describe, expect, it, vi } from "vitest";
import { donationClient } from "./donation";

describe("donationClient", () => {
  it("download POSTs session_ids and returns a Blob", async () => {
    const blob = new Blob(["zip"]);
    const fetchSpy = vi.fn(async () => ({ ok: true, blob: async () => blob }));
    const api = donationClient(fetchSpy as never);
    const result = await api.download(["a", "b"]);
    expect(result).toBe(blob);
    expect(fetchSpy).toHaveBeenCalledWith("/api/sessions/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_ids: ["a", "b"] }),
    });
  });

  it("donate surfaces the detail error from the body", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: false,
      status: 400,
      json: async () => ({ detail: "no valid session ids" }),
    }));
    const api = donationClient(fetchSpy as never);
    await expect(api.donate(["x"])).rejects.toThrow("no valid session ids");
  });

  it("donate returns the parsed DonateResult on OK", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => ({ total: 1, donated: 1, donation_id: "d1", errors: [] }),
    }));
    const api = donationClient(fetchSpy as never);
    const result = await api.donate(["x"]);
    expect(result.donated).toBe(1);
    expect(result.donation_id).toBe("d1");
  });
});
