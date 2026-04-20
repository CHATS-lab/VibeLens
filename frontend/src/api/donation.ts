import type { DonateResult, DonationHistoryResponse } from "../types";
import type { FetchWithToken } from "./analysis";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface DonationClient {
  download: (sessionIds: string[]) => Promise<Blob>;
  donate: (sessionIds: string[]) => Promise<DonateResult>;
  history: () => Promise<DonationHistoryResponse>;
}

export function donationClient(fetchWithToken: FetchWithToken): DonationClient {
  return {
    download: async (sessionIds) => {
      const res = await fetchWithToken("/api/sessions/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: sessionIds }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.blob();
    },
    donate: async (sessionIds) => {
      const res = await fetchWithToken("/api/sessions/donate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: sessionIds }),
      });
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try {
          const data = await res.json();
          msg = data?.detail || msg;
        } catch {
          /* ignore */
        }
        throw new Error(msg);
      }
      return res.json();
    },
    history: async () => jsonOrThrow(await fetchWithToken("/api/sessions/donations/history")),
  };
}
