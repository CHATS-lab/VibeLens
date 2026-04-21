import { ExternalLink } from "lucide-react";
import type { VersionInfo } from "../api/version";
import type { UseVersionResult } from "../hooks/use-version";
import { CopyButton } from "./ui/copy-button";
import { LoadingSpinner } from "./ui/loading-spinner";

const GITHUB_RELEASE_URL = "https://github.com/CHATS-lab/VibeLens/releases/tag/v";

interface VersionSectionProps {
  version: UseVersionResult;
}

export function VersionSection({ version }: VersionSectionProps) {
  const { info, effectiveState, skippedVersion, skipLatest, unskip, retry } = version;

  return (
    <section className="flex flex-col gap-2 pb-4 mb-4 border-b border-default">
      <h3 className="text-sm font-semibold text-primary">About</h3>
      <Body
        state={effectiveState}
        info={info}
        skippedVersion={skippedVersion}
        onSkip={skipLatest}
        onUnskip={unskip}
        onRetry={retry}
      />
    </section>
  );
}

interface BodyProps {
  state: UseVersionResult["effectiveState"];
  info: VersionInfo | null;
  skippedVersion: string | null;
  onSkip: () => void;
  onUnskip: () => void;
  onRetry: () => void;
}

function Body({ state, info, skippedVersion, onSkip, onUnskip, onRetry }: BodyProps) {
  if (state === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <LoadingSpinner />
        <span>Checking for updates…</span>
      </div>
    );
  }

  if (state === "check_failed") {
    return (
      <div className="flex items-center gap-3 text-sm">
        <span className="text-secondary">
          {info ? `VibeLens v${info.current}` : "VibeLens"}
        </span>
        <button onClick={onRetry} className="text-xs text-accent-cyan hover:underline">
          Check for updates
        </button>
      </div>
    );
  }

  if (!info) return null;

  if (state === "dev_build") {
    return (
      <div className="text-sm text-secondary">
        VibeLens v{info.current}
        <span className="ml-2 text-xs text-muted">Dev build (ahead of PyPI)</span>
      </div>
    );
  }

  if (state === "update_available" && info.latest) {
    return <UpdateAvailableBlock info={info} onSkip={onSkip} />;
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="text-sm text-secondary">
        VibeLens v{info.current}
        <span className="ml-2 text-xs text-muted">Up to date</span>
      </div>
      {skippedVersion && info.latest === skippedVersion && (
        <button
          onClick={onUnskip}
          className="text-xs text-accent-cyan hover:underline self-start"
        >
          You chose to skip v{skippedVersion}. Unskip.
        </button>
      )}
    </div>
  );
}

interface UpdateBlockProps {
  info: VersionInfo;
  onSkip: () => void;
}

function UpdateAvailableBlock({ info, onSkip }: UpdateBlockProps) {
  const { current, latest, install_method: method, install_commands: commands } = info;
  const recommended =
    method in commands
      ? commands[method as keyof typeof commands]
      : commands.pip;
  const otherMethods = (
    Object.keys(commands) as Array<keyof typeof commands>
  ).filter((key) => key !== method);

  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm text-secondary">
        VibeLens v{current} → v{latest} available
      </div>
      <CommandRow text={recommended} />
      <div className="flex items-center gap-4 text-xs">
        <a
          href={`${GITHUB_RELEASE_URL}${latest}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-accent-cyan hover:underline"
        >
          View what's new <ExternalLink className="w-3 h-3" />
        </a>
        <button
          onClick={onSkip}
          className="text-muted hover:text-secondary hover:underline"
        >
          Skip this version
        </button>
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted hover:text-secondary">
          Other install methods
        </summary>
        <ul className="mt-2 flex flex-col gap-1">
          {otherMethods.map((key) => (
            <li key={key}>
              <CommandRow text={commands[key]} />
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function CommandRow({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 rounded bg-control border border-card px-3 py-2 font-mono text-xs text-primary">
      <span className="flex-1 select-all">{text}</span>
      <CopyButton text={text} />
    </div>
  );
}
