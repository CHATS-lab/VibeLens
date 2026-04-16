import { Check, Copy, ExternalLink, Heart } from "lucide-react";
import { useCallback, useState } from "react";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "./modal";
import { buildWithdrawUrl } from "./donation-constants";
import type { DonateResult } from "../types";

interface DonateResultDialogProps {
  result: DonateResult;
  onClose: () => void;
}

type CopyState = "idle" | "copied" | "failed";

const COPY_FEEDBACK_MS = 1500;

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to textarea fallback */
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

export function DonateResultDialog({ result, onClose }: DonateResultDialogProps) {
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const hasErrors = result.errors.length > 0;
  const donationId = result.donation_id ?? "";

  const handleCopy = useCallback(async () => {
    if (!donationId) return;
    const ok = await copyToClipboard(donationId);
    setCopyState(ok ? "copied" : "failed");
    window.setTimeout(() => setCopyState("idle"), COPY_FEEDBACK_MS);
  }, [donationId]);

  const copyLabel =
    copyState === "copied" ? "Copied!" : copyState === "failed" ? "Copy failed" : "Copy";
  const copyIcon =
    copyState === "copied" ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />;
  const copyClasses =
    copyState === "copied"
      ? "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/40"
      : copyState === "failed"
        ? "text-rose-700 dark:text-rose-300 bg-rose-100 dark:bg-rose-950/30 border-rose-300 dark:border-rose-700/50"
        : "text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-800/40 hover:bg-rose-100 dark:hover:bg-rose-950/40";

  return (
    <Modal onClose={onClose} maxWidth="max-w-lg">
      <ModalHeader onClose={onClose}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-rose-600/20">
            <Heart className="w-5 h-5 text-rose-600 dark:text-rose-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-primary">
              {hasErrors ? "Completed with errors" : "Donation complete"}
            </h2>
            <p className="text-xs text-muted">Thanks for supporting open research</p>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        {donationId && (
          <div className="rounded-lg border border-card bg-control/40 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-wider text-muted mb-1">
                  Donation ID
                </div>
                <div className="font-mono text-sm text-primary select-all break-all">
                  {donationId}
                </div>
              </div>
              <button
                onClick={handleCopy}
                className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium border rounded-md transition-all duration-150 ${copyClasses}`}
              >
                {copyIcon}
                {copyLabel}
              </button>
            </div>
          </div>
        )}

        {donationId && (
          <p className="text-xs text-muted">
            Want to withdraw this donation?{" "}
            <a
              href={buildWithdrawUrl(donationId)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-rose-600 dark:text-rose-400 hover:underline"
            >
              Request withdrawal
              <ExternalLink className="w-3 h-3" />
            </a>
          </p>
        )}

        {hasErrors && (
          <div className="rounded-lg border border-red-200 dark:border-red-800/30 bg-red-50 dark:bg-red-900/20 px-4 py-3">
            <p className="text-xs font-semibold text-red-700 dark:text-red-300 mb-1">
              {result.errors.length} error{result.errors.length !== 1 ? "s" : ""}
            </p>
            <ul className="text-xs text-red-700 dark:text-red-300 space-y-0.5">
              {result.errors.slice(0, 3).map((err, i) => (
                <li key={i} className="font-mono break-all">
                  {err.session_id ? `${err.session_id}: ` : ""}
                  {err.error}
                </li>
              ))}
            </ul>
          </div>
        )}
      </ModalBody>

      <ModalFooter>
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-muted hover:text-secondary hover:bg-control-hover border border-card hover:border-hover rounded-lg transition"
        >
          Close
        </button>
      </ModalFooter>
    </Modal>
  );
}
