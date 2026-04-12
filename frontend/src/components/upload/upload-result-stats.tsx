import { MessageSquare, Shield, Zap } from "lucide-react";
import type { UploadResult } from "../../types";

export function ResultStats({ result }: { result: UploadResult }) {
  const hasErrors = result.errors.length > 0;
  const totalPrivacy = result.secrets_redacted + result.paths_anonymized + result.pii_redacted;

  return (
    <div className="space-y-3">
      {/* Import stats */}
      <div className="rounded-lg border border-card bg-subtle">
        <div className="grid grid-cols-3 divide-x divide-zinc-700/30">
          <StatBox icon={<MessageSquare className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" />} label="Sessions" value={result.sessions_parsed} />
          <StatBox icon={<Zap className="w-3.5 h-3.5 text-accent-cyan" />} label="Steps" value={result.steps_stored} />
          <StatBox label="Skipped" value={result.skipped} />
        </div>
      </div>

      {/* Privacy protection summary */}
      {totalPrivacy > 0 && (
        <div className="rounded-lg border border-emerald-200 dark:border-emerald-700/30 bg-emerald-50 dark:bg-emerald-950/10 px-4 py-3">
          <div className="flex items-center gap-2 mb-2.5">
            <Shield className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span className="text-sm font-semibold text-primary">Privacy Protection</span>
          </div>
          <p className="text-xs text-secondary mb-2">
            Your data was automatically cleaned before storage. The following sensitive items were removed:
          </p>
          <div className="grid grid-cols-3 gap-2">
            {result.secrets_redacted > 0 && (
              <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-md px-2.5 py-2 text-center">
                <p className="text-lg font-semibold font-mono text-emerald-700 dark:text-emerald-400">{result.secrets_redacted.toLocaleString()}</p>
                <p className="text-[10px] text-emerald-600 dark:text-emerald-300/70 mt-0.5">API keys & tokens</p>
              </div>
            )}
            {result.paths_anonymized > 0 && (
              <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-md px-2.5 py-2 text-center">
                <p className="text-lg font-semibold font-mono text-emerald-700 dark:text-emerald-400">{result.paths_anonymized.toLocaleString()}</p>
                <p className="text-[10px] text-emerald-600 dark:text-emerald-300/70 mt-0.5">File paths</p>
              </div>
            )}
            {result.pii_redacted > 0 && (
              <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-md px-2.5 py-2 text-center">
                <p className="text-lg font-semibold font-mono text-emerald-700 dark:text-emerald-400">{result.pii_redacted.toLocaleString()}</p>
                <p className="text-[10px] text-emerald-600 dark:text-emerald-300/70 mt-0.5">Personal info</p>
              </div>
            )}
          </div>
        </div>
      )}

      {hasErrors && (
        <div className="p-3 bg-accent-rose-subtle border border-rose-200 dark:border-rose-800/40 rounded-lg text-xs text-accent-rose space-y-1">
          <p className="font-semibold text-rose-700 dark:text-rose-200">
            {result.sessions_parsed > 0 ? "Some files had errors:" : "Errors:"}
          </p>
          {result.errors.slice(0, 5).map((e, i) => (
            <p key={i} className="text-rose-600 dark:text-rose-400">
              {e.filename ? `${e.filename}: ` : ""}
              {e.error}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function StatBox({ icon, label, value }: { icon?: React.ReactNode; label: string; value: number }) {
  return (
    <div className="px-3 py-2.5 text-center">
      <div className="flex items-center justify-center gap-1.5 mb-1">
        {icon}
        <p className="text-xs text-muted">{label}</p>
      </div>
      <p className="text-primary font-mono text-lg font-semibold">{value.toLocaleString()}</p>
    </div>
  );
}
