import { Check, Copy, ExternalLink, Heart, History, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Modal, ModalBody, ModalHeader } from "../ui/modal";
import { buildWithdrawUrl, formatDonatedAt } from "./donation-constants";
import { donationClient } from "../../api/donation";
import { useCopyFeedback } from "../../hooks/use-copy-feedback";
import type { DonationHistoryEntry } from "../../types";

interface DonationHistoryDialogProps {
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onClose: () => void;
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; entries: DonationHistoryEntry[] };

function HistoryRow({ entry }: { entry: DonationHistoryEntry }) {
  const { copied, copy } = useCopyFeedback();

  const handleCopy = useCallback(() => {
    copy(entry.donation_id);
  }, [copy, entry.donation_id]);

  const formattedAt = useMemo(() => formatDonatedAt(entry.donated_at), [entry.donated_at]);

  return (
    <div className="border-b border-card hover:bg-control/60 px-4 py-3 transition">
      <div className="flex items-center justify-between gap-3">
        <div className="font-mono text-sm text-primary select-all break-all">
          {entry.donation_id}
        </div>
        <button
          onClick={handleCopy}
          aria-label="Copy donation ID"
          className={`shrink-0 p-1.5 rounded transition ${
            copied
              ? "text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/20"
              : "text-dimmed hover:text-secondary hover:bg-control-hover"
          }`}
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
      <div className="mt-1 flex items-center justify-between gap-3 text-xs text-muted">
        <span>
          {entry.session_count} session{entry.session_count !== 1 ? "s" : ""} · {formattedAt}
        </span>
        <a
          href={buildWithdrawUrl(entry.donation_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-rose-600 dark:text-rose-400 hover:underline"
        >
          Withdraw
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
}

export function DonationHistoryDialog({ fetchWithToken, onClose }: DonationHistoryDialogProps) {
  const api = useMemo(() => donationClient(fetchWithToken), [fetchWithToken]);
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const body = await api.history();
      setState({ kind: "ready", entries: body.entries });
    } catch (err) {
      setState({ kind: "error", message: String(err) });
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Modal onClose={onClose} maxWidth="max-w-lg">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-600/20">
            <History className="w-5 h-5 text-cyan-600 dark:text-cyan-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-primary">Donation history</h2>
            <p className="text-xs text-muted">Your past donations from this browser</p>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        {state.kind === "loading" && (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-5 h-5 animate-spin text-zinc-400 dark:text-cyan-400/60" />
          </div>
        )}

        {state.kind === "error" && (
          <div className="rounded-lg border border-red-200 dark:border-red-800/30 bg-red-50 dark:bg-red-900/20 px-4 py-3 flex items-center justify-between gap-3">
            <span className="text-xs text-red-700 dark:text-red-300">
              Couldn't load donation history ({state.message}).
            </span>
            <button
              onClick={() => void load()}
              className="shrink-0 px-2.5 py-1 text-xs text-red-700 dark:text-red-300 border border-red-300 dark:border-red-700/40 hover:bg-red-100 dark:hover:bg-red-950/30 rounded transition"
            >
              Retry
            </button>
          </div>
        )}

        {state.kind === "ready" && state.entries.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-2">
            <Heart className="w-8 h-8 text-faint" />
            <p className="text-sm text-muted">No donations yet</p>
            <p className="text-xs text-dimmed">Donate sessions to see them listed here.</p>
          </div>
        )}

        {state.kind === "ready" && state.entries.length > 0 && (
          <div className="-mx-5 -my-4">
            {state.entries.map((entry) => (
              <HistoryRow key={entry.donation_id} entry={entry} />
            ))}
          </div>
        )}
      </ModalBody>
    </Modal>
  );
}
