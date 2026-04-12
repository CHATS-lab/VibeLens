import {
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  FileArchive,
  Loader2,
  MessageSquare,
  Shield,
  Trash2,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../app";
import type { AgentType, OSPlatform, UploadCommands, UploadResult } from "../types";
import { CopyButton } from "./copy-button";

interface UploadDialogProps {
  onClose: () => void;
  onComplete: () => void;
}

type Step = "select" | "upload" | "confirm" | "result";

const AGENT_OPTIONS: { type: AgentType; label: string }[] = [
  { type: "claude_code", label: "Claude Code" },
  { type: "claude_code_web", label: "Claude Web" },
  { type: "codex", label: "Codex CLI" },
  { type: "gemini", label: "Gemini CLI" },
];

const OS_OPTIONS: { platform: OSPlatform; label: string }[] = [
  { platform: "macos", label: "macOS" },
  { platform: "linux", label: "Linux" },
  { platform: "windows", label: "Windows" },
];

const AGENT_LABELS: Record<AgentType, string> = {
  claude_code: "Claude Code",
  claude_code_web: "Claude Web",
  codex: "Codex CLI",
  gemini: "Gemini CLI",
};

const DEFAULT_AGENT: AgentType = "claude_code";
const DEFAULT_OS: OSPlatform = "macos";

export function UploadDialog({ onClose, onComplete }: UploadDialogProps) {
  const { fetchWithToken, sessionToken, maxZipBytes } = useAppContext();
  const maxZipMB = Math.round(maxZipBytes / (1024 * 1024));
  const [step, setStep] = useState<Step>("select");
  const [agentType, setAgentType] = useState<AgentType>(DEFAULT_AGENT);
  const [osPlatform, setOsPlatform] = useState<OSPlatform>(DEFAULT_OS);
  const [commands, setCommands] = useState<UploadCommands | null>(null);
  const [commandLoading, setCommandLoading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState<"sending" | "processing">("sending");
  const [result, setResult] = useState<UploadResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const isWebExport = agentType === "claude_code_web";

  // Fetch command when entering upload step (skip for web exports)
  useEffect(() => {
    if (step !== "upload" || isWebExport) return;
    setCommandLoading(true);
    fetchWithToken(
      `/api/upload/commands?agent_type=${agentType}&os_platform=${osPlatform}`
    )
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: UploadCommands) => setCommands(data))
      .catch(() =>
        setCommands({ command: "# Failed to load command", description: "" })
      )
      .finally(() => setCommandLoading(false));
  }, [step, agentType, osPlatform, isWebExport, fetchWithToken]);

  const fileTooLarge = file ? file.size > maxZipBytes : false;

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setResult(null);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.name.toLowerCase().endsWith(".zip")) {
      setFile(dropped);
    }
  }, []);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setResult(null);
      const selected = e.target.files?.[0];
      if (selected && selected.name.toLowerCase().endsWith(".zip")) {
        setFile(selected);
      }
      e.target.value = "";
    },
    []
  );

  const handleUpload = useCallback(() => {
    if (!file) return;
    setStep("result");
    setUploading(true);
    setResult(null);
    setUploadProgress(0);
    setUploadPhase("sending");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("agent_type", agentType);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload/zip");
    xhr.setRequestHeader("X-Session-Token", sessionToken);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        setUploadProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.upload.onload = () => {
      setUploadPhase("processing");
    };

    xhr.onload = () => {
      const errorResult = (msg: string) => ({
        files_received: 1,
        sessions_parsed: 0,
        steps_stored: 0,
        skipped: 0,
        secrets_redacted: 0,
        paths_anonymized: 0,
        pii_redacted: 0,
        errors: [{ filename: file.name, error: msg }],
      });

      if (xhr.status === 413) {
        setResult(errorResult(
          "File too large for the server's upload limit. If behind nginx, increase client_max_body_size in your nginx config."
        ));
        setUploading(false);
        return;
      }

      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          setResult(data);
        } else {
          setResult(errorResult(data.detail || `HTTP ${xhr.status}`));
        }
      } catch {
        // Strip HTML tags from error responses (e.g., nginx error pages)
        const cleaned = xhr.responseText?.replace(/<[^>]*>/g, "").trim();
        setResult(errorResult(cleaned || `HTTP ${xhr.status}`));
      }
      setUploading(false);
    };

    xhr.onerror = () => {
      setResult({
        files_received: 1,
        sessions_parsed: 0,
        steps_stored: 0,
        skipped: 0,
        secrets_redacted: 0,
        paths_anonymized: 0,
        pii_redacted: 0,
        errors: [{ filename: file.name, error: "Network error" }],
      });
      setUploading(false);
    };

    xhr.send(formData);
  }, [file, agentType, sessionToken]);

  const handleDone = useCallback(() => {
    if (result && result.sessions_parsed > 0) {
      onComplete();
    }
    onClose();
  }, [result, onClose, onComplete]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-overlay backdrop-blur-sm"
        onClick={uploading ? undefined : onClose}
      />
      <div className="relative bg-panel border border-card rounded-lg shadow-2xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-default">
          <div className="flex items-center gap-2">
            {(step === "upload" || step === "confirm") && !uploading && (
              <button
                onClick={() => setStep(step === "confirm" ? "upload" : "select")}
                className="text-dimmed hover:text-secondary transition"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
            )}
            <h2 className="text-sm font-semibold text-primary">
              Upload Conversation Data
            </h2>
          </div>
          <button
            onClick={onClose}
            disabled={uploading}
            className="text-dimmed hover:text-secondary transition disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-5">
          {step === "select" && (
            <div className="space-y-5">
              <p className="text-sm text-secondary">
                {isWebExport
                  ? "Which data source are you uploading from?"
                  : "Which agent and OS are you using?"}
              </p>

              {/* Agent selector */}
              <SelectorRow
                label="Source"
                options={AGENT_OPTIONS.map((o) => ({
                  value: o.type,
                  label: o.label,
                }))}
                selected={agentType}
                onSelect={(v) => setAgentType(v as AgentType)}
              />

              {/* OS selector — hidden for web exports */}
              {!isWebExport && (
                <SelectorRow
                  label="Your OS"
                  options={OS_OPTIONS.map((o) => ({
                    value: o.platform,
                    label: o.label,
                  }))}
                  selected={osPlatform}
                  onSelect={(v) => setOsPlatform(v as OSPlatform)}
                />
              )}

              <div className="flex justify-end pt-1">
                <button
                  onClick={() => setStep("upload")}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition"
                >
                  Next
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {step === "upload" && (
            <div className="space-y-4">
              {/* Instructions area — web export vs CLI command */}
              {isWebExport ? (
                <WebExportInstructions />
              ) : (
                <div className="space-y-1.5">
                  <p className="text-sm text-secondary">
                    Run this command in your terminal, then upload the zip.
                  </p>
                  {commandLoading ? (
                    <div className="flex items-center justify-center py-4 bg-canvas border border-default rounded-lg">
                      <Loader2 className="w-4 h-4 text-dimmed animate-spin" />
                    </div>
                  ) : (
                    <div className="relative">
                      <pre className="bg-canvas border border-default rounded-lg p-3 pr-10 text-xs text-accent-cyan font-mono overflow-x-auto whitespace-pre-wrap break-all">
                        {commands?.command ?? ""}
                      </pre>
                      {commands && (
                        <div className="absolute top-2 right-2">
                          <CopyButton text={commands.command} />
                        </div>
                      )}
                    </div>
                  )}
                  {commands?.description && (
                    <p className="text-sm text-secondary">{commands.description}</p>
                  )}
                </div>
              )}

              {/* Drop zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleFileDrop}
                onClick={() => inputRef.current?.click()}
                className={`flex flex-col items-center justify-center gap-2 p-6 border-2 border-dashed rounded-lg cursor-pointer transition ${
                  dragOver
                    ? "border-violet-400 bg-violet-500/10"
                    : "border-card hover:border-zinc-500 bg-subtle"
                }`}
              >
                <FileArchive
                  className={`w-7 h-7 ${dragOver ? "text-violet-400" : "text-dimmed"}`}
                />
                <p className="text-sm text-secondary">Drop .zip file here</p>
                <p className="text-xs text-dimmed">or click to browse (max {maxZipMB} MB)</p>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={handleFileSelect}
                />
              </div>

              {/* Selected file + action button */}
              {file && (
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs text-secondary truncate min-w-0">
                    <FileArchive className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                    <span className="truncate">{file.name}</span>
                    <span className={`shrink-0 ${fileTooLarge ? "text-rose-400" : "text-dimmed"}`}>
                      ({(file.size / (1024 * 1024)).toFixed(1)} MB)
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        setResult(null);
                      }}
                      className="text-dimmed hover:text-rose-400 transition shrink-0"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <button
                    onClick={() => setStep("confirm")}
                    disabled={fileTooLarge}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    Upload
                  </button>
                </div>
              )}

              {/* Size warning */}
              {file && fileTooLarge && (
                <p className="text-xs text-rose-400">
                  File exceeds the {maxZipMB} MB limit. Try excluding large sessions or splitting the archive.
                </p>
              )}
            </div>
          )}

          {step === "confirm" && file && (
            <div className="space-y-5">
              <p className="text-sm text-secondary">
                Ready to upload? Please confirm the details below.
              </p>

              <div className="bg-subtle border border-card rounded-lg p-4 space-y-2.5">
                <div className="flex items-center gap-2 text-sm text-secondary">
                  <FileArchive className="w-4 h-4 text-violet-400 shrink-0" />
                  <span className="truncate">{file.name}</span>
                </div>
                <div className="flex items-center gap-4 text-xs text-muted">
                  <span>{(file.size / (1024 * 1024)).toFixed(1)} MB</span>
                  <span>{AGENT_LABELS[agentType]}</span>
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setStep("upload")}
                  className="px-4 py-1.5 text-xs text-muted hover:text-secondary border border-card hover:border-zinc-500 rounded transition"
                >
                  Back
                </button>
                <button
                  onClick={handleUpload}
                  className="flex items-center gap-1.5 px-4 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition"
                >
                  <Upload className="w-3.5 h-3.5" />
                  Confirm Upload
                </button>
              </div>
            </div>
          )}

          {step === "result" && (
            <div className="space-y-5">
              {uploading ? (
                <div className="space-y-5">
                  <div className="flex flex-col items-center gap-4 py-6">
                    <div className="relative">
                      <div className="w-16 h-16 rounded-full border-2 border-violet-500/30 flex items-center justify-center">
                        <Loader2 className="w-7 h-7 text-violet-400 animate-spin" />
                      </div>
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-semibold text-primary">
                        {uploadPhase === "sending" ? "Uploading your data" : "Processing sessions"}
                      </p>
                      <p className="text-xs text-muted mt-1">
                        {uploadPhase === "sending"
                          ? "Sending your file to the server"
                          : "Extracting, parsing, and scrubbing sensitive data"}
                      </p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="w-full h-2 bg-control rounded-full overflow-hidden">
                      {uploadPhase === "sending" ? (
                        <div
                          className="h-full bg-gradient-to-r from-violet-600 to-violet-400 rounded-full transition-all duration-300"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      ) : (
                        <div className="h-full bg-gradient-to-r from-violet-600 to-violet-400 rounded-full animate-pulse w-full" />
                      )}
                    </div>
                    <p className="text-xs text-muted text-center">
                      {uploadPhase === "sending"
                        ? `${uploadProgress}% of ${((file?.size ?? 0) / (1024 * 1024)).toFixed(1)} MB uploaded`
                        : "This may take a moment for large archives"}
                    </p>
                  </div>
                </div>
              ) : result ? (
                <div className="space-y-4">
                  {result.errors.length > 0 && result.sessions_parsed === 0 ? (
                    <div className="flex flex-col items-center gap-2 py-4">
                      <div className="w-14 h-14 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
                        <AlertCircle className="w-7 h-7 text-rose-400" />
                      </div>
                      <p className="text-base font-semibold text-rose-300">Upload failed</p>
                      <p className="text-xs text-muted">No sessions could be imported from this file.</p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3 py-4">
                      <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                        <CheckCircle2 className="w-7 h-7 text-emerald-400" />
                      </div>
                      <div className="text-center">
                        <p className="text-base font-semibold text-primary">Upload complete</p>
                        <p className="text-sm text-muted mt-0.5">
                          {result.sessions_parsed} {result.sessions_parsed === 1 ? "session" : "sessions"} imported with {result.steps_stored.toLocaleString()} steps
                        </p>
                      </div>
                    </div>
                  )}
                  <ResultStats result={result} />
                  <div className="flex justify-end">
                    <button
                      onClick={handleDone}
                      className="px-4 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition"
                    >
                      Done
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const WEB_EXPORT_STEPS = [
  { num: "1", text: "Open claude.ai and go to Settings" },
  { num: "2", text: 'Scroll to "Export Data" and click Export' },
  { num: "3", text: "Wait for the email, then download the zip" },
  { num: "4", text: "Upload the downloaded zip below" },
];

function WebExportInstructions() {
  return (
    <div className="space-y-2">
      <p className="text-sm text-secondary">
        Export your data from claude.ai, then upload the zip.
      </p>
      <div className="bg-canvas border border-default rounded-lg p-3 space-y-2">
        {WEB_EXPORT_STEPS.map((s) => (
          <div key={s.num} className="flex items-start gap-2.5">
            <span className="flex items-center justify-center w-5 h-5 rounded-full bg-violet-600/20 text-violet-400 text-[10px] font-bold shrink-0 mt-px">
              {s.num}
            </span>
            <span className="text-xs text-secondary">{s.text}</span>
          </div>
        ))}
      </div>
      <a
        href="https://claude.ai/settings"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 transition"
      >
        Open claude.ai Settings
        <ExternalLink className="w-3 h-3" />
      </a>
    </div>
  );
}

function SelectorRow({
  label,
  options,
  selected,
  onSelect,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string;
  onSelect: (value: string) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-muted w-14 shrink-0">{label}</span>
      <div className="flex gap-1.5">
        {options.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onSelect(opt.value)}
            className={`px-3 py-1 text-xs rounded-full transition ${
              selected === opt.value
                ? "bg-violet-600 text-white"
                : "bg-control text-muted border border-card hover:border-zinc-500 hover:text-secondary"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ResultStats({ result }: { result: UploadResult }) {
  const hasErrors = result.errors.length > 0;
  const totalPrivacy = result.secrets_redacted + result.paths_anonymized + result.pii_redacted;

  return (
    <div className="space-y-3">
      {/* Import stats */}
      {/* Import stats */}
      <div className="rounded-lg border border-card bg-subtle">
        <div className="grid grid-cols-3 divide-x divide-zinc-700/30">
          <StatBox icon={<MessageSquare className="w-3.5 h-3.5 text-violet-400" />} label="Sessions" value={result.sessions_parsed} />
          <StatBox icon={<Zap className="w-3.5 h-3.5 text-accent-cyan" />} label="Steps" value={result.steps_stored} />
          <StatBox label="Skipped" value={result.skipped} />
        </div>
      </div>

      {/* Privacy protection summary */}
      {totalPrivacy > 0 && (
        <div className="rounded-lg border border-emerald-700/30 bg-emerald-950/10 px-4 py-3">
          <div className="flex items-center gap-2 mb-2.5">
            <Shield className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-semibold text-primary">Privacy Protection</span>
          </div>
          <p className="text-xs text-secondary mb-2">
            Your data was automatically cleaned before storage. The following sensitive items were removed:
          </p>
          <div className="grid grid-cols-3 gap-2">
            {result.secrets_redacted > 0 && (
              <div className="bg-emerald-900/20 rounded-md px-2.5 py-2 text-center">
                <p className="text-lg font-semibold font-mono text-emerald-400">{result.secrets_redacted.toLocaleString()}</p>
                <p className="text-[10px] text-emerald-300/70 mt-0.5">API keys & tokens</p>
              </div>
            )}
            {result.paths_anonymized > 0 && (
              <div className="bg-emerald-900/20 rounded-md px-2.5 py-2 text-center">
                <p className="text-lg font-semibold font-mono text-emerald-400">{result.paths_anonymized.toLocaleString()}</p>
                <p className="text-[10px] text-emerald-300/70 mt-0.5">File paths</p>
              </div>
            )}
            {result.pii_redacted > 0 && (
              <div className="bg-emerald-900/20 rounded-md px-2.5 py-2 text-center">
                <p className="text-lg font-semibold font-mono text-emerald-400">{result.pii_redacted.toLocaleString()}</p>
                <p className="text-[10px] text-emerald-300/70 mt-0.5">Personal info</p>
              </div>
            )}
          </div>
        </div>
      )}

      {hasErrors && (
        <div className="p-3 bg-accent-rose-subtle border border-accent-rose rounded-lg text-xs text-accent-rose space-y-1">
          <p className="font-semibold text-rose-200">
            {result.sessions_parsed > 0 ? "Some files had errors:" : "Errors:"}
          </p>
          {result.errors.slice(0, 5).map((e, i) => (
            <p key={i} className="text-rose-400">
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
