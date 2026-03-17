import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  FileArchive,
  Loader2,
  Monitor,
  Terminal,
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

type WizardStep =
  | "select_agent"
  | "select_os"
  | "show_command"
  | "upload_zip"
  | "result";

const STEP_ORDER: WizardStep[] = [
  "select_agent",
  "select_os",
  "show_command",
  "upload_zip",
  "result",
];

const STEP_LABELS = ["Agent", "OS", "Command", "Upload", "Done"];

interface AgentOption {
  type: AgentType;
  label: string;
  description: string;
}

const AGENT_OPTIONS: AgentOption[] = [
  {
    type: "claude_code",
    label: "Claude Code",
    description: "Anthropic's CLI coding agent",
  },
  {
    type: "codex",
    label: "Codex CLI",
    description: "OpenAI's terminal coding agent",
  },
  {
    type: "gemini",
    label: "Gemini CLI",
    description: "Google's CLI coding agent",
  },
];

interface OSOption {
  platform: OSPlatform;
  label: string;
}

const OS_OPTIONS: OSOption[] = [
  { platform: "macos", label: "macOS" },
  { platform: "linux", label: "Linux" },
  { platform: "windows", label: "Windows" },
];

export function UploadDialog({ onClose, onComplete }: UploadDialogProps) {
  const { fetchWithToken } = useAppContext();
  const [step, setStep] = useState<WizardStep>("select_agent");
  const [agentType, setAgentType] = useState<AgentType | null>(null);
  const [osPlatform, setOsPlatform] = useState<OSPlatform | null>(null);
  const [commands, setCommands] = useState<UploadCommands | null>(null);
  const [commandLoading, setCommandLoading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const currentIndex = STEP_ORDER.indexOf(step);
  const canGoBack =
    currentIndex > 0 && step !== "result" && !uploading && !commandLoading;

  const goBack = useCallback(() => {
    const idx = STEP_ORDER.indexOf(step);
    if (idx > 0) setStep(STEP_ORDER[idx - 1]);
  }, [step]);

  const selectAgent = useCallback((agent: AgentType) => {
    setAgentType(agent);
    setStep("select_os");
  }, []);

  const selectOS = useCallback(
    (platform: OSPlatform) => {
      setOsPlatform(platform);
      setStep("show_command");
    },
    []
  );

  useEffect(() => {
    if (step !== "show_command" || !agentType || !osPlatform) return;

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

  const handleFileDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.name.toLowerCase().endsWith(".zip")) {
      setFile(dropped);
    }
  }, []);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files?.[0];
      if (selected && selected.name.toLowerCase().endsWith(".zip")) {
        setFile(selected);
      }
      e.target.value = "";
    },
    []
  );

  const handleUpload = useCallback(async () => {
    if (!file || !agentType) return;
    setUploading(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("agent_type", agentType);

    try {
      const res = await fetchWithToken("/api/upload/zip", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => `HTTP ${res.status}`);
        setResult({
          files_received: 1,
          sessions_parsed: 0,
          messages_stored: 0,
          skipped: 0,
          errors: [{ filename: file.name, error: text }],
        });
      } else {
        setResult(await res.json());
      }
    } catch (err) {
      setResult({
        files_received: 1,
        sessions_parsed: 0,
        messages_stored: 0,
        skipped: 0,
        errors: [{ filename: file.name, error: String(err) }],
      });
    }
    setUploading(false);
    setStep("result");
  }, [file, agentType, fetchWithToken]);

  const handleDone = useCallback(() => {
    if (result && result.sessions_parsed > 0) {
      onComplete();
    }
    onClose();
  }, [result, onClose, onComplete]);

  const handleDeleteUploaded = useCallback(async () => {
    await fetchWithToken("/api/upload/sessions", { method: "DELETE" });
    onComplete();
    onClose();
  }, [onComplete, onClose, fetchWithToken]);

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
            {canGoBack && (
              <button
                onClick={goBack}
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

        {/* Step indicators */}
        <div className="flex items-center justify-center gap-1.5 px-5 py-3 border-b border-zinc-800/50">
          {STEP_LABELS.map((label, i) => (
            <div key={label} className="flex items-center gap-1.5">
              <div
                className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition ${
                  i === currentIndex
                    ? "bg-violet-600/30 text-violet-300 border border-violet-500/40"
                    : i < currentIndex
                      ? "bg-zinc-700/50 text-zinc-400"
                      : "bg-zinc-800/50 text-zinc-600"
                }`}
              >
                {i < currentIndex ? (
                  <CheckCircle2 className="w-2.5 h-2.5" />
                ) : (
                  <span className="w-2.5 text-center">{i + 1}</span>
                )}
                {label}
              </div>
              {i < STEP_LABELS.length - 1 && (
                <ChevronRight className="w-3 h-3 text-zinc-700" />
              )}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="px-5 py-5 min-h-[200px]">
          {step === "select_agent" && (
            <AgentStep onSelect={selectAgent} />
          )}
          {step === "select_os" && (
            <OSStep onSelect={selectOS} />
          )}
          {step === "show_command" && (
            <CommandStep
              commands={commands}
              loading={commandLoading}
              onNext={() => setStep("upload_zip")}
            />
          )}
          {step === "upload_zip" && (
            <ZipUploadStep
              file={file}
              dragOver={dragOver}
              uploading={uploading}
              inputRef={inputRef}
              onDrop={handleFileDrop}
              onDragOver={() => setDragOver(true)}
              onDragLeave={() => setDragOver(false)}
              onFileSelect={handleFileSelect}
              onClickZone={() => inputRef.current?.click()}
              onRemoveFile={() => setFile(null)}
              onUpload={handleUpload}
            />
          )}
          {step === "result" && result && (
            <ResultStep
              result={result}
              onDone={handleDone}
              onDelete={handleDeleteUploaded}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function AgentStep({ onSelect }: { onSelect: (agent: AgentType) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-300">
        Which coding agent do you use?
      </p>
      <div className="grid gap-2">
        {AGENT_OPTIONS.map((opt) => (
          <button
            key={opt.type}
            onClick={() => onSelect(opt.type)}
            className="flex items-center gap-3 p-3 bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/50 hover:border-violet-500/40 rounded-lg transition text-left group"
          >
            <Terminal className="w-5 h-5 text-zinc-500 group-hover:text-violet-400 transition shrink-0" />
            <div>
              <p className="text-sm font-medium text-zinc-200">
                {opt.label}
              </p>
              <p className="text-xs text-zinc-500">{opt.description}</p>
            </div>
            <ChevronRight className="w-4 h-4 text-zinc-600 ml-auto" />
          </button>
        ))}
      </div>
    </div>
  );
}

function OSStep({ onSelect }: { onSelect: (platform: OSPlatform) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-300">
        What's your operating system?
      </p>
      <div className="grid gap-2">
        {OS_OPTIONS.map((opt) => (
          <button
            key={opt.platform}
            onClick={() => onSelect(opt.platform)}
            className="flex items-center gap-3 p-3 bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/50 hover:border-violet-500/40 rounded-lg transition text-left group"
          >
            <Monitor className="w-5 h-5 text-zinc-500 group-hover:text-violet-400 transition shrink-0" />
            <p className="text-sm font-medium text-zinc-200">{opt.label}</p>
            <ChevronRight className="w-4 h-4 text-zinc-600 ml-auto" />
          </button>
        ))}
      </div>
    </div>
  );
}

function CommandStep({
  commands,
  loading,
  onNext,
}: {
  commands: UploadCommands | null;
  loading: boolean;
  onNext: () => void;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-300">
        Run this command in your terminal, then upload the generated zip file.
      </p>
      {commands && (
        <>
          {commands.description && (
            <p className="text-xs text-zinc-500">{commands.description}</p>
          )}
          <div className="relative">
            <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 pr-10 text-xs text-cyan-300 font-mono overflow-x-auto whitespace-pre-wrap break-all">
              {commands.command}
            </pre>
            <div className="absolute top-2 right-2">
              <CopyButton text={commands.command} />
            </div>
          </div>
        </>
      )}
      <div className="flex justify-end">
        <button
          onClick={onNext}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition"
        >
          Next
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

function ZipUploadStep({
  file,
  dragOver,
  uploading,
  inputRef,
  onDrop,
  onDragOver,
  onDragLeave,
  onFileSelect,
  onClickZone,
  onRemoveFile,
  onUpload,
}: {
  file: File | null;
  dragOver: boolean;
  uploading: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onDrop: (e: React.DragEvent) => void;
  onDragOver: () => void;
  onDragLeave: () => void;
  onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onClickZone: () => void;
  onRemoveFile: () => void;
  onUpload: () => void;
}) {
  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          onDragOver();
        }}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={onClickZone}
        className={`flex flex-col items-center justify-center gap-2 p-8 border-2 border-dashed rounded-lg cursor-pointer transition ${
          dragOver
            ? "border-violet-400 bg-violet-500/10"
            : "border-zinc-700 hover:border-zinc-500 bg-zinc-800/30"
        }`}
      >
        <FileArchive
          className={`w-8 h-8 ${dragOver ? "text-violet-400" : "text-zinc-500"}`}
        />
        <p className="text-sm text-zinc-300">Drop your .zip file here</p>
        <p className="text-xs text-zinc-500">
          Or click to browse
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={onFileSelect}
        />
      </div>

      {/* Selected file */}
      {file && (
        <div className="flex items-center justify-between px-3 py-2 bg-zinc-800/50 rounded text-xs">
          <div className="flex items-center gap-2 text-zinc-300 truncate mr-2">
            <FileArchive className="w-3.5 h-3.5 text-violet-400 shrink-0" />
            <span className="truncate">{file.name}</span>
            <span className="text-zinc-500 shrink-0">
              ({(file.size / (1024 * 1024)).toFixed(1)} MB)
            </span>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRemoveFile();
            }}
            className="text-zinc-500 hover:text-rose-400 transition shrink-0"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Upload button */}
      <div className="flex justify-end">
        <button
          onClick={onUpload}
          disabled={!file || uploading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {uploading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Uploading...
            </>
          ) : (
            <>
              <Upload className="w-3.5 h-3.5" />
              Upload
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function ResultStep({
  result,
  onDone,
  onDelete,
}: {
  result: UploadResult;
  onDone: () => void;
  onDelete: () => void;
}) {
  const hasErrors = result.errors.length > 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 text-sm">
        <StatBox label="Sessions Parsed" value={result.sessions_parsed} />
        <StatBox label="Messages Stored" value={result.messages_stored} />
        <StatBox label="Files Received" value={result.files_received} />
        <StatBox label="Skipped" value={result.skipped} />
      </div>

      {hasErrors && (
        <div className="p-3 bg-rose-900/20 border border-rose-800/50 rounded text-xs text-rose-300 space-y-1">
          <p className="font-medium">Errors:</p>
          {result.errors.slice(0, 5).map((e, i) => (
            <p key={i} className="text-rose-400">
              {e.filename ? `${e.filename}: ` : ""}
              {e.error}
            </p>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          onClick={onDelete}
          className="text-[11px] text-zinc-500 hover:text-rose-400 transition underline underline-offset-2"
        >
          Delete all uploaded sessions
        </button>
        <button
          onClick={onDone}
          className="px-3 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition"
        >
          Done
        </button>
      </div>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-zinc-800/50 rounded px-3 py-2">
      <p className="text-[11px] text-zinc-500">{label}</p>
      <p className="text-zinc-200 font-mono">{value}</p>
    </div>
  );
}
