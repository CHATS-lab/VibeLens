import { Loader2, Download, BarChart3 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Message, SessionDetail } from "../types";
import { MessageBlock } from "./message-block";
import { formatTokens } from "../utils";

interface SessionViewProps {
  sessionId: string;
}

export function SessionView({ sessionId }: SessionViewProps) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    setDetail(null);

    fetch(`/api/sessions/${sessionId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
        return res.json();
      })
      .then((data: SessionDetail) => setDetail(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-cyan-500 animate-spin mx-auto mb-2" />
          <p className="text-sm text-zinc-400">Loading session...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-4">
        <div className="text-center bg-rose-900/20 border border-rose-800 rounded-lg p-6 max-w-md">
          <p className="text-sm font-semibold text-rose-300 mb-2">Failed to load session</p>
          <p className="text-xs text-rose-400 mb-4 font-mono break-all">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-3 py-1 bg-rose-700/50 hover:bg-rose-700 rounded text-xs text-rose-200 transition"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!detail) return null;

  const messages = detail.messages as Message[];
  const visibleMessages = messages.filter((m) => {
    if (m.role === "user") {
      if (Array.isArray(m.content)) {
        const hasText = (m.content).some(
          (b) => b.type === "text" && b.text?.trim()
        );
        if (!hasText) return false;
      }
    }
    return m.role === "user" || m.role === "assistant";
  });

  const stats = detail.summary;

  return (
    <div className="h-full overflow-y-auto flex flex-col">
      {/* Session Header */}
      <div className="sticky top-0 bg-zinc-900/95 border-b border-zinc-800 px-6 py-4 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-start justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">
                {stats.first_message ? `${stats.first_message.slice(0, 60)}...` : 'Session'}
              </h2>
              <p className="text-xs text-zinc-400 mt-1">
                {stats.message_count} messages • {stats.tool_call_count} tools • {stats.duration || 0}s
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => navigator.clipboard.writeText(JSON.stringify(detail, null, 2))}
                className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition text-xs"
                title="Export session"
              >
                <Download className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Token Stats */}
          {(stats.total_input_tokens !== undefined ||
            stats.total_output_tokens !== undefined) && (
            <div className="grid grid-cols-4 gap-2 text-xs">
              <div className="bg-zinc-800/50 rounded px-2 py-1.5">
                <p className="text-zinc-500">Input</p>
                <p className="text-cyan-300 font-mono">
                  {formatTokens(stats.total_input_tokens || 0)}
                </p>
              </div>
              <div className="bg-zinc-800/50 rounded px-2 py-1.5">
                <p className="text-zinc-500">Output</p>
                <p className="text-cyan-300 font-mono">
                  {formatTokens(stats.total_output_tokens || 0)}
                </p>
              </div>
              <div className="bg-zinc-800/50 rounded px-2 py-1.5">
                <p className="text-zinc-500">Cache Read</p>
                <p className="text-green-300 font-mono">
                  {formatTokens(stats.total_cache_read || 0)}
                </p>
              </div>
              <div className="bg-zinc-800/50 rounded px-2 py-1.5">
                <p className="text-zinc-500">Models</p>
                <p className="text-amber-300 font-mono">
                  {stats.models?.join(", ") || "N/A"}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-3">
          {visibleMessages.length === 0 ? (
            <div className="text-center text-zinc-500 text-sm py-8">
              <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>No messages to display</p>
            </div>
          ) : (
            visibleMessages.map((msg) => (
              <MessageBlock key={msg.uuid} message={msg} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
