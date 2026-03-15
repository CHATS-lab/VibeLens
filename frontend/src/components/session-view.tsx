import {
  Loader2,
  Download,
  BarChart3,
  Bot,
  Clock,
  MessageSquare,
  Wrench,
  FolderOpen,
  Database,
  HardDrive,
  Cpu,
  Calendar,
  Hash,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Message, SessionDetail, SubAgentSession, DataSourceType } from "../types";
import { MessageBlock } from "./message-block";
import { SubAgentBlock } from "./sub-agent-block";
import { PromptNavPanel } from "./prompt-nav-panel";
import { formatTokens, formatDuration, extractUserText } from "../utils";

interface SessionViewProps {
  sessionId: string;
}

export function SessionView({ sessionId }: SessionViewProps) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activePromptUuid, setActivePromptUuid] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const isNavigatingRef = useRef(false);

  useEffect(() => {
    setLoading(true);
    setError("");
    setDetail(null);
    setActivePromptUuid(null);

    fetch(`/api/sessions/${sessionId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
        return res.json();
      })
      .then((data: SessionDetail) => setDetail(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const subSessions = (detail?.sub_sessions || []) as SubAgentSession[];

  const subSessionsBySpawn = useMemo(() => {
    const map = new Map<number, SubAgentSession[]>();
    const orphans: SubAgentSession[] = [];
    for (const sub of subSessions) {
      if (sub.spawn_index !== null && sub.spawn_index !== undefined) {
        const existing = map.get(sub.spawn_index) || [];
        existing.push(sub);
        map.set(sub.spawn_index, existing);
      } else {
        orphans.push(sub);
      }
    }
    return { map, orphans };
  }, [detail]);

  const messages = (detail?.messages || []) as Message[];

  const userPromptUuids = useMemo(() => {
    return messages
      .filter((m) => m.role === "user" && extractUserText(m))
      .map((m) => m.uuid);
  }, [messages]);

  // IntersectionObserver to track which user prompt is currently visible
  useEffect(() => {
    if (!messagesRef.current || userPromptUuids.length < 2) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (isNavigatingRef.current) return;
        // Pick the topmost intersecting entry to avoid flickering
        let topEntry: IntersectionObserverEntry | null = null;
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          if (!topEntry || entry.boundingClientRect.top < topEntry.boundingClientRect.top) {
            topEntry = entry;
          }
        }
        if (topEntry) {
          setActivePromptUuid(topEntry.target.id.replace("msg-", ""));
        }
      },
      {
        root: messagesRef.current,
        rootMargin: "-10% 0px -80% 0px",
        threshold: 0,
      }
    );

    for (const uuid of userPromptUuids) {
      const el = document.getElementById(`msg-${uuid}`);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, [userPromptUuids]);

  const SCROLL_SUPPRESS_MS = 800;

  const handlePromptNavigate = useCallback((uuid: string) => {
    const el = document.getElementById(`msg-${uuid}`);
    if (!el) return;
    // Suppress observer during programmatic scroll to prevent wrong highlight
    isNavigatingRef.current = true;
    setActivePromptUuid(uuid);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => {
      isNavigatingRef.current = false;
    }, SCROLL_SUPPRESS_MS);
  }, []);

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

  const stats = detail.summary;
  const promptCount = userPromptUuids.length;
  const totalTokens =
    (stats.total_input_tokens || 0) +
    (stats.total_output_tokens || 0);

  const isVisibleMessage = (m: Message): boolean => {
    if (m.role === "user") {
      if (Array.isArray(m.content)) {
        const hasText = (m.content).some(
          (b) => b.type === "text" && b.text?.trim()
        );
        if (!hasText) return false;
      }
    }
    return m.role === "user" || m.role === "assistant";
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Session Header */}
      <div className="shrink-0 bg-zinc-900/95 border-b border-zinc-800 px-6 py-4">
        <div className="max-w-7xl mx-auto">
          {/* Row 1: Title + Meta Pills */}
          <div className="flex items-start justify-between mb-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold text-zinc-100 truncate">
                {stats.first_message ? stats.first_message.slice(0, 80) : "Session"}
              </h2>
              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                <MetaPill
                  icon={<Clock className="w-3 h-3" />}
                  label={formatDuration(stats.duration)}
                  color="text-cyan-400"
                />
                <MetaPill
                  icon={<MessageSquare className="w-3 h-3" />}
                  label={`${promptCount} turn${promptCount !== 1 ? "s" : ""}`}
                  color="text-blue-400"
                />
                <MetaPill
                  icon={<Wrench className="w-3 h-3" />}
                  label={`${stats.tool_call_count} tools`}
                  color="text-amber-400"
                />
                {subSessions.length > 0 && (
                  <MetaPill
                    icon={<Bot className="w-3 h-3" />}
                    label={`${subSessions.length} sub-agent${subSessions.length > 1 ? "s" : ""}`}
                    color="text-violet-400"
                  />
                )}
                <SourceBadge sourceType={stats.source_type} />
                {stats.project_name && (
                  <MetaPill
                    icon={<FolderOpen className="w-3 h-3" />}
                    label={stats.project_name}
                    color="text-zinc-300"
                  />
                )}
                {stats.timestamp && (
                  <MetaPill
                    icon={<Calendar className="w-3 h-3" />}
                    label={formatCreatedTime(stats.timestamp)}
                    color="text-zinc-400"
                  />
                )}
                {stats.models && stats.models.length > 0 && (
                  <MetaPill
                    icon={<Cpu className="w-3 h-3" />}
                    label={stats.models.join(", ")}
                    color="text-amber-300"
                  />
                )}
                <MetaPill
                  icon={<Hash className="w-3 h-3" />}
                  label={stats.session_id.slice(0, 8)}
                  color="text-zinc-500"
                />
              </div>
            </div>
            <div className="flex gap-2 shrink-0 ml-3">
              <button
                onClick={() => navigator.clipboard.writeText(JSON.stringify(detail, null, 2))}
                className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition text-xs"
                title="Export session"
              >
                <Download className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Row 2: Token Stats */}
          {(stats.total_input_tokens !== undefined ||
            stats.total_output_tokens !== undefined) && (
            <div className="grid grid-cols-5 gap-2 text-xs">
              <TokenStat label="Input" value={stats.total_input_tokens || 0} color="text-cyan-300" />
              <TokenStat label="Output" value={stats.total_output_tokens || 0} color="text-cyan-300" />
              <TokenStat label="Cache Read" value={stats.total_cache_read || 0} color="text-green-300" />
              <TokenStat label="Cache Write" value={stats.total_cache_write || 0} color="text-violet-300" />
              <TokenStat label="Total" value={totalTokens} color="text-amber-300" />
            </div>
          )}
        </div>
      </div>

      {/* Two-column body: Messages + Prompt Nav */}
      <div className="flex-1 flex min-h-0">
        {/* Messages */}
        <div ref={messagesRef} className="flex-1 overflow-y-auto">
          <div className="max-w-5xl mx-auto px-4 py-6 space-y-3">
            {messages.length === 0 ? (
              <div className="text-center text-zinc-500 text-sm py-8">
                <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No messages to display</p>
              </div>
            ) : (
              <>
                {messages.map((msg, idx) => {
                  const visible = isVisibleMessage(msg);
                  const spawnedSubs = subSessionsBySpawn.map.get(idx);
                  if (!visible && !spawnedSubs) return null;
                  return (
                    <div key={msg.uuid} id={`msg-${msg.uuid}`}>
                      {visible && <MessageBlock message={msg} />}
                      {spawnedSubs?.map((sub) => (
                        <div key={sub.agent_id} className="mt-2">
                          <SubAgentBlock subSession={sub} />
                        </div>
                      ))}
                    </div>
                  );
                })}
                {subSessionsBySpawn.orphans.map((sub) => (
                  <SubAgentBlock key={sub.agent_id} subSession={sub} />
                ))}
              </>
            )}
          </div>
        </div>

        {/* Prompt Navigation Sidebar */}
        <PromptNavPanel
          messages={messages}
          activePromptUuid={activePromptUuid}
          onNavigate={handlePromptNavigate}
        />
      </div>
    </div>
  );
}

function MetaPill({
  icon,
  label,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800/60 text-[11px] ${color}`}
    >
      {icon}
      <span className="truncate max-w-[180px]">{label}</span>
    </span>
  );
}

const SOURCE_BADGE_STYLES: Record<DataSourceType, string> = {
  local: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  mongodb: "bg-green-500/15 text-green-400 border-green-500/25",
  huggingface: "bg-yellow-500/15 text-yellow-400 border-yellow-500/25",
};

const SOURCE_ICONS: Record<DataSourceType, React.ReactNode> = {
  local: <HardDrive className="w-3 h-3" />,
  mongodb: <Database className="w-3 h-3" />,
  huggingface: <Database className="w-3 h-3" />,
};

function SourceBadge({ sourceType }: { sourceType: DataSourceType }) {
  if (!sourceType) return null;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] border ${SOURCE_BADGE_STYLES[sourceType] || SOURCE_BADGE_STYLES.local}`}
    >
      {SOURCE_ICONS[sourceType] || SOURCE_ICONS.local}
      {sourceType}
    </span>
  );
}

function TokenStat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="bg-zinc-800/50 rounded px-2 py-1.5">
      <p className="text-zinc-500">{label}</p>
      <p className={`${color} font-mono`}>{formatTokens(value)}</p>
    </div>
  );
}

function formatCreatedTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return timestamp;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
