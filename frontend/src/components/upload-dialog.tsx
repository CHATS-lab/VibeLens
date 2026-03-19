import {
  ArrowLeft,
  ChevronRight,
  FileArchive,
  Loader2,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../app";
import type { AgentType, OSPlatform, UploadCommands, UploadResult } from "../types";
import { CopyButton } from "./copy-button";

interface UploadDialogProps {
  onClose: () => void;
  onComplete: () => void;
}

type Step = "select" | "upload";

const AGENT_OPTIONS: { type: AgentType; label: string }[] = [
  { type: "claude_code", label: "Claude Code" },
  { type: "codex", label: "Codex CLI" },
  { type: "gemini", label: "Gemini CLI" },
];

const OS_OPTIONS: { platform: OSPlatform; label: string }[] = [
  { platform: "macos", label: "macOS" },
  { platform: "linux", label: "Linux" },
  { platform: "windows", label: "Windows" },
];

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

  // Fetch command when entering upload step
  useEffect(() => {
    if (step !== "upload") return;
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
  }, [step, agentType, osPlatform, fetchWithToken]);

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
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          setResult(data);
        } else {
          setResult({
            files_received: 1,
            sessions_parsed: 0,
            steps_stored: 0,
            skipped: 0,
            errors: [{ filename: file.name, error: data.detail || `HTTP ${xhr.status}` }],
          });
        }
      } catch {
        setResult({
          files_received: 1,
          sessions_parsed: 0,
          steps_stored: 0,
          skipped: 0,
          errors: [{ filename: file.name, error: xhr.responseText || `HTTP ${xhr.status}` }],
        });
      }
      setUploading(false);
    };

    xhr.onerror = () => {
      setResult({
        files_received: 1,
        sessions_parsed: 0,
        steps_stored: 0,
        skipped: 0,
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

  const hasResult = result !== null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={uploading ? undefined : onClose}
      />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            {step === "upload" && !uploading && (
              <button
                onClick={() => setStep("select")}
                className="text-zinc-500 hover:text-zinc-300 transition"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
            )}
            <h2 className="text-sm font-semibold text-zinc-100">
              Upload Conversation Data
            </h2>
          </div>
          <button
            onClick={onClose}
            disabled={uploading}
            className="text-zinc-500 hover:text-zinc-300 transition disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-5">
          {step === "select" && (
            <div className="space-y-5">
              <p className="text-sm text-zinc-300">
                Which agent and OS are you using?
              </p>

              {/* Agent selector */}
              <SelectorRow
                label="Agent"
                options={AGENT_OPTIONS.map((o) => ({
                  value: o.type,
                  label: o.label,
                }))}
                selected={agentType}
                onSelect={(v) => setAgentType(v as AgentType)}
              />

              {/* OS selector */}
              <SelectorRow
                label="Your OS"
                options={OS_OPTIONS.map((o) => ({
                  value: o.platform,
                  label: o.label,
                }))}
                selected={osPlatform}
                onSelect={(v) => setOsPlatform(v as OSPlatform)}
              />

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
              {/* Command area */}
              <div className="space-y-1.5">
                <p className="text-sm text-zinc-300">
                  Run this command in your terminal, then upload the zip.
                </p>
                {commands?.description && (
                  <p className="text-xs text-zinc-500">{commands.description}</p>
                )}
                {commandLoading ? (
                  <div className="flex items-center justify-center py-4 bg-zinc-950 border border-zinc-800 rounded-lg">
                    <Loader2 className="w-4 h-4 text-zinc-500 animate-spin" />
                  </div>
                ) : (
                  <div className="relative">
                    <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 pr-10 text-xs text-cyan-300 font-mono overflow-x-auto whitespace-pre-wrap break-all">
                      {commands?.command ?? ""}
                    </pre>
                    {commands && (
                      <div className="absolute top-2 right-2">
                        <CopyButton text={commands.command} />
                      </div>
                    )}
                  </div>
                )}
              </div>

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
                    : "border-zinc-700 hover:border-zinc-500 bg-zinc-800/30"
                }`}
              >
                <FileArchive
                  className={`w-7 h-7 ${dragOver ? "text-violet-400" : "text-zinc-500"}`}
                />
                <p className="text-sm text-zinc-300">Drop .zip file here</p>
                <p className="text-xs text-zinc-500">or click to browse (max {maxZipMB} MB)</p>
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
                  <div className="flex items-center gap-2 text-xs text-zinc-300 truncate min-w-0">
                    <FileArchive className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                    <span className="truncate">{file.name}</span>
                    <span className={`shrink-0 ${fileTooLarge ? "text-rose-400" : "text-zinc-500"}`}>
                      ({(file.size / (1024 * 1024)).toFixed(1)} MB)
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        setResult(null);
                      }}
                      className="text-zinc-500 hover:text-rose-400 transition shrink-0"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <button
                    onClick={hasResult ? handleDone : handleUpload}
                    disabled={uploading || fileTooLarge}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                  >
                    {uploading ? (
                      uploadPhase === "processing" ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Processing...
                        </>
                      ) : (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          {uploadProgress}%
                        </>
                      )
                    ) : hasResult ? (
                      "Done"
                    ) : (
                      <>
                        <Upload className="w-3.5 h-3.5" />
                        Upload
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Size warning */}
              {file && fileTooLarge && (
                <p className="text-xs text-rose-400">
                  File exceeds the {maxZipMB} MB limit. Try excluding large sessions or splitting the archive.
                </p>
              )}

              {/* Progress bar */}
              {uploading && (
                <div className="space-y-1.5">
                  <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    {uploadPhase === "sending" ? (
                      <div
                        className="h-full bg-violet-500 rounded-full transition-all duration-300"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    ) : (
                      <div className="h-full bg-violet-500 rounded-full animate-pulse w-full" />
                    )}
                  </div>
                  <p className="text-[10px] text-zinc-500 text-center">
                    {uploadPhase === "sending"
                      ? `Uploading — ${uploadProgress}% of ${((file?.size ?? 0) / (1024 * 1024)).toFixed(0)} MB`
                      : "Server is extracting and parsing sessions…"}
                  </p>
                </div>
              )}

              {/* Inline result */}
              {result && <ResultStats result={result} />}
            </div>
          )}
        </div>
      </div>
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
      <span className="text-xs text-zinc-400 w-14 shrink-0">{label}</span>
      <div className="flex gap-1.5">
        {options.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onSelect(opt.value)}
            className={`px-3 py-1 text-xs rounded-full transition ${
              selected === opt.value
                ? "bg-violet-600 text-white"
                : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:border-zinc-500 hover:text-zinc-200"
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

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-2 text-xs">
        <StatBox label="Sessions" value={result.sessions_parsed} />
        <StatBox label="Steps" value={result.steps_stored} />
        <StatBox label="Skipped" value={result.skipped} />
      </div>
      {hasErrors && (
        <div className="p-2.5 bg-rose-900/20 border border-rose-800/50 rounded text-xs text-rose-300 space-y-0.5">
          <p className="font-medium">Errors:</p>
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

function StatBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-zinc-800/50 rounded px-2.5 py-1.5">
      <p className="text-[10px] text-zinc-500">{label}</p>
      <p className="text-zinc-200 font-mono text-sm">{value}</p>
    </div>
  );
}
