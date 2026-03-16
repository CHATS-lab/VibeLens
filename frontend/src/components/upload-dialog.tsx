import { FileUp, Loader2, Trash2, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import type { UploadResult } from "../types";

interface UploadDialogProps {
  onClose: () => void;
  onComplete: () => void;
}

type DialogPhase = "idle" | "uploading" | "result";

const ACCEPTED_EXTENSIONS = ".json,.jsonl";

export function UploadDialog({ onClose, onComplete }: UploadDialogProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<DialogPhase>("idle");
  const [result, setResult] = useState<UploadResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const valid = Array.from(incoming).filter((f) => {
      const ext = f.name.split(".").pop()?.toLowerCase();
      return ext === "json" || ext === "jsonl";
    });
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name));
      return [...prev, ...valid.filter((f) => !existing.has(f.name))];
    });
  }, []);

  const removeFile = useCallback((name: string) => {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      addFiles(e.dataTransfer.files);
    },
    [addFiles]
  );

  const handleUpload = useCallback(async () => {
    if (files.length === 0) return;
    setPhase("uploading");

    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => `HTTP ${res.status}`);
        setResult({
          files_received: files.length,
          sessions_parsed: 0,
          messages_stored: 0,
          skipped: 0,
          errors: [{ filename: "", error: text }],
        });
      } else {
        setResult(await res.json());
      }
    } catch (err) {
      setResult({
        files_received: files.length,
        sessions_parsed: 0,
        messages_stored: 0,
        skipped: 0,
        errors: [{ filename: "", error: String(err) }],
      });
    }
    setPhase("result");
  }, [files]);

  const handleDone = useCallback(() => {
    if (result && result.sessions_parsed > 0) {
      onComplete();
    }
    onClose();
  }, [result, onClose, onComplete]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={phase === "uploading" ? undefined : onClose}
      />
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-100">
            Upload Conversation Files
          </h2>
          <button
            onClick={onClose}
            disabled={phase === "uploading"}
            className="text-zinc-500 hover:text-zinc-300 transition disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {phase === "result" && result ? (
            <ResultView result={result} />
          ) : (
            <>
              {/* Drop zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                className={`flex flex-col items-center justify-center gap-2 p-8 border-2 border-dashed rounded-lg cursor-pointer transition ${
                  dragOver
                    ? "border-violet-400 bg-violet-500/10"
                    : "border-zinc-700 hover:border-zinc-500 bg-zinc-800/30"
                }`}
              >
                <FileUp
                  className={`w-8 h-8 ${dragOver ? "text-violet-400" : "text-zinc-500"}`}
                />
                <p className="text-sm text-zinc-300">
                  Drop .json / .jsonl files here
                </p>
                <p className="text-xs text-zinc-500">
                  Claude Code, Codex, Gemini, Dataclaw
                </p>
                <input
                  ref={inputRef}
                  type="file"
                  accept={ACCEPTED_EXTENSIONS}
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files) addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
              </div>

              {/* File list */}
              {files.length > 0 && (
                <ul className="space-y-1 max-h-40 overflow-y-auto">
                  {files.map((f) => (
                    <li
                      key={f.name}
                      className="flex items-center justify-between px-3 py-1.5 bg-zinc-800/50 rounded text-xs"
                    >
                      <span className="text-zinc-300 truncate mr-2">
                        {f.name}
                      </span>
                      <button
                        onClick={() => removeFile(f.name)}
                        className="text-zinc-500 hover:text-rose-400 transition shrink-0"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-zinc-800">
          {phase === "result" ? (
            <button
              onClick={handleDone}
              className="px-3 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                disabled={phase === "uploading"}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={files.length === 0 || phase === "uploading"}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white bg-violet-600 hover:bg-violet-500 rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {phase === "uploading" ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <FileUp className="w-3.5 h-3.5" />
                    Upload ({files.length})
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultView({ result }: { result: UploadResult }) {
  const hasErrors = result.errors.length > 0;
  return (
    <div className="space-y-2 text-sm">
      <div className="grid grid-cols-2 gap-2">
        <StatBox label="Sessions Parsed" value={result.sessions_parsed} />
        <StatBox label="Messages Stored" value={result.messages_stored} />
        <StatBox label="Files Received" value={result.files_received} />
        <StatBox label="Skipped" value={result.skipped} />
      </div>
      {hasErrors && (
        <div className="mt-2 p-3 bg-rose-900/20 border border-rose-800/50 rounded text-xs text-rose-300 space-y-1">
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
    <div className="bg-zinc-800/50 rounded px-3 py-2">
      <p className="text-[11px] text-zinc-500">{label}</p>
      <p className="text-zinc-200 font-mono">{value}</p>
    </div>
  );
}
