import { Check, Copy, Loader2, Share2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import { sessionsClient } from "../../api/sessions";
import type { Trajectory } from "../../types";
import { Modal, ModalBody, ModalHeader } from "../ui/modal";

type ShareState =
  | { kind: "hidden" }
  | { kind: "demo-blocked" }
  | { kind: "sharing" }
  | { kind: "ready"; url: string; copied: boolean };

interface UseShareSessionResult {
  /** Spread onto the share button. */
  buttonProps: {
    onClick: () => void;
    disabled: boolean;
    children: React.ReactNode;
  };
  /** Render the modals at the top level of the component tree. */
  dialogs: React.ReactNode;
}

/** Drive the Share-session flow: opens the dialog, creates a share link,
 * and renders both the success modal and the demo-mode blocker modal.
 */
export function useShareSession(
  sessionId: string,
  trajectories: Trajectory[],
): UseShareSessionResult {
  const { fetchWithToken, appMode } = useAppContext();
  const api = useMemo(() => sessionsClient(fetchWithToken), [fetchWithToken]);
  const [state, setState] = useState<ShareState>({ kind: "hidden" });

  const openShare = useCallback(async () => {
    const isUploaded = trajectories.some((t) => !!t._upload_id);
    if (appMode === "demo" && isUploaded) {
      setState({ kind: "demo-blocked" });
      return;
    }
    setState({ kind: "sharing" });
    try {
      const data = await api.createShare(sessionId);
      const shareUrl = `${window.location.origin}/?share=${data.session_id}`;
      setState({ kind: "ready", url: shareUrl, copied: false });
    } catch (err) {
      console.error("Share failed:", err);
      setState({ kind: "hidden" });
    }
  }, [api, appMode, sessionId, trajectories]);

  const handleCopy = useCallback(async (url: string) => {
    await navigator.clipboard.writeText(url);
    setState({ kind: "ready", url, copied: true });
  }, []);

  const close = useCallback(() => setState({ kind: "hidden" }), []);

  return {
    buttonProps: {
      onClick: openShare,
      disabled: state.kind === "sharing",
      children:
        state.kind === "sharing" ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Share2 className="w-4 h-4" />
        ),
    },
    dialogs: (
      <>
        {state.kind === "ready" && (
          <Modal onClose={close} maxWidth="max-w-lg">
            <ModalHeader onClose={close}>
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-md bg-accent-cyan-muted border border-accent-cyan">
                  <Share2 className="w-4 h-4 text-accent-cyan" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-primary">Share session</h2>
                  <p className="text-xs text-dimmed mt-0.5">
                    Anyone with this link can view the session
                  </p>
                </div>
              </div>
            </ModalHeader>
            <ModalBody>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={state.url}
                  onFocus={(e) => e.target.select()}
                  className="flex-1 bg-control border border-card rounded-lg px-3 py-2.5 text-sm text-secondary font-mono select-all focus:outline-none focus:border-accent-cyan-focus transition"
                />
                <button
                  onClick={() => handleCopy(state.url)}
                  className={`shrink-0 flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-xs font-medium transition ${
                    state.copied
                      ? "bg-emerald-700 text-white"
                      : "bg-cyan-700 hover:bg-cyan-600 text-white"
                  }`}
                >
                  {state.copied ? (
                    <Check className="w-3.5 h-3.5" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                  {state.copied ? "Copied!" : "Copy link"}
                </button>
              </div>
            </ModalBody>
          </Modal>
        )}

        {state.kind === "demo-blocked" && (
          <Modal onClose={close} maxWidth="max-w-md">
            <ModalBody>
              <div className="text-center bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-lg p-6">
                <p className="text-sm font-semibold text-rose-700 dark:text-rose-300 mb-2">
                  Cannot share uploaded sessions
                </p>
                <p className="text-xs text-rose-600 dark:text-rose-400">
                  Uploaded sessions are temporary and only visible in your browser tab.
                  Install VibeLens locally to share sessions with a permanent link.
                </p>
                <a
                  href="https://github.com/chats-lab/VibeLens"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block mt-4 px-4 py-2 rounded text-xs font-medium bg-rose-200 hover:bg-rose-300 dark:bg-rose-800/50 dark:hover:bg-rose-700/50 text-rose-700 dark:text-rose-200 transition"
                >
                  Install VibeLens
                </a>
              </div>
            </ModalBody>
          </Modal>
        )}
      </>
    ),
  };
}
