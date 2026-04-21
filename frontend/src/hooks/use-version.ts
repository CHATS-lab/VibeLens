import { useCallback, useEffect, useMemo, useState } from "react";
import type { VersionClient, VersionInfo } from "../api/version";
import {
  clearSkippedVersion,
  getSkippedVersion,
  setSkippedVersion,
} from "../lib/skip-version";

export type VersionEffectiveState =
  | "loading"
  | "up_to_date"
  | "dev_build"
  | "update_available"
  | "check_failed";

type Status =
  | { kind: "loading" }
  | { kind: "ok"; info: VersionInfo }
  | { kind: "failed" };

export interface UseVersionResult {
  info: VersionInfo | null;
  skippedVersion: string | null;
  effectiveState: VersionEffectiveState;
  skipLatest: () => void;
  unskip: () => void;
  retry: () => void;
}

export function useVersion(client: VersionClient): UseVersionResult {
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  const [skippedVersion, setSkippedState] = useState<string | null>(() =>
    getSkippedVersion(),
  );
  const [fetchCounter, setFetchCounter] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus({ kind: "loading" });
    client
      .get()
      .then((data) => {
        if (cancelled) return;
        setStatus({ kind: "ok", info: data });
      })
      .catch(() => {
        if (cancelled) return;
        setStatus({ kind: "failed" });
      });
    return () => {
      cancelled = true;
    };
  }, [client, fetchCounter]);

  const info = status.kind === "ok" ? status.info : null;

  const skipLatest = useCallback(() => {
    if (!info?.latest) return;
    setSkippedVersion(info.latest);
    setSkippedState(info.latest);
  }, [info?.latest]);

  const unskip = useCallback(() => {
    clearSkippedVersion();
    setSkippedState(null);
  }, []);

  const retry = useCallback(() => setFetchCounter((n) => n + 1), []);

  const effectiveState = useMemo<VersionEffectiveState>(() => {
    if (status.kind === "loading") return "loading";
    if (status.kind === "failed") return "check_failed";
    const { info } = status;
    if (info.latest === null) return "check_failed";
    if (info.is_dev_build) return "dev_build";
    if (info.update_available && skippedVersion !== info.latest) {
      return "update_available";
    }
    return "up_to_date";
  }, [status, skippedVersion]);

  return {
    info,
    skippedVersion,
    effectiveState,
    skipLatest,
    unskip,
    retry,
  };
}
