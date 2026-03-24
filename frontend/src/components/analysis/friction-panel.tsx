import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  FileText,
  Footprints,
  Hash,
  History,
  Loader2,
  Pencil,
  Play,
  Plus,
  Search,
  Shield,
  Sparkles,
  Target,
  Wrench,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAppContext } from "../../app";
import type {
  ClaudeMdSuggestion,
  FrictionAnalysisResult,
  FrictionEvent,
  LLMStatus,
  ModeSummary,
} from "../../types";
import { formatCost, formatDuration, formatTokens } from "../../utils";
import { SEVERITY_COLORS, SESSION_ID_SHORT, SESSION_ID_MEDIUM } from "../../styles";
import { CopyButton } from "../copy-button";
import { FrictionHistory } from "./friction-history";

const SEVERITY_LABELS: Record<number, string> = {
  1: "Minor",
  2: "Low",
  3: "Moderate",
  4: "High",
  5: "Critical",
};

const SEVERITY_DESCRIPTIONS: Record<number, string> = {
  1: "Minor — Minimal inconvenience, negligible wasted effort",
  2: "Low — Noticeable friction, a few wasted steps",
  3: "Moderate — Clear wasted effort and rework",
  4: "High — Significant blocker, many wasted steps",
  5: "Critical — Session blocker, major rework required",
};

interface FrictionPanelProps {
  checkedIds: Set<string>;
}

export function FrictionPanel({ checkedIds }: FrictionPanelProps) {
  const { fetchWithToken } = useAppContext();
  const [result, setResult] = useState<FrictionAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  const [historyRefresh, setHistoryRefresh] = useState(0);

  const refreshLlmStatus = useCallback(async () => {
    try {
      const res = await fetchWithToken("/api/llm/status");
      if (res.ok) setLlmStatus(await res.json());
    } catch {
      /* ignore — status check is best-effort */
    }
  }, [fetchWithToken]);

  useEffect(() => {
    refreshLlmStatus();
  }, [refreshLlmStatus]);

  const handleRunAnalysis = useCallback(async () => {
    if (checkedIds.size === 0) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithToken("/api/analysis/friction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: [...checkedIds] }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      const data: FrictionAnalysisResult = await res.json();
      setResult(data);
      setHistoryRefresh((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [checkedIds, fetchWithToken]);

  const handleHistorySelect = useCallback((loaded: FrictionAnalysisResult) => {
    setResult(loaded);
    setShowHistory(false);
  }, []);

  const handleNewAnalysis = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-10 h-10 text-cyan-400 animate-spin" />
          <div className="text-center">
            <p className="text-sm font-medium text-zinc-200">
              Analyzing {checkedIds.size} session{checkedIds.size !== 1 ? "s" : ""} for friction
            </p>
            <p className="text-xs text-zinc-500 mt-1">This may take a moment</p>
          </div>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="h-full flex">
        <div className="flex-1">
          <EmptyState
            checkedCount={checkedIds.size}
            error={error}
            onRun={handleRunAnalysis}
            llmStatus={llmStatus}
            fetchWithToken={fetchWithToken}
            onLlmConfigured={refreshLlmStatus}
          />
        </div>
        <div className="w-56 shrink-0 border-l border-zinc-800 bg-zinc-900/50 overflow-y-auto p-3">
          <FrictionHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
          <ResultHeader result={result} onRerun={handleRunAnalysis} onNew={handleNewAnalysis} />
          <SummarySection summary={result.summary} topMitigation={result.top_mitigation} />
          {result.mode_summary.length > 0 && (
            <ModeSummarySection modes={result.mode_summary} />
          )}
          {result.claude_md_suggestions.length > 0 && (
            <SuggestionsSection suggestions={result.claude_md_suggestions} />
          )}
          <EventsSection events={result.events} sessionIds={result.session_ids} />
          <AnalysisMeta result={result} />
        </div>
      </div>
      {showHistory ? (
        <div className="w-56 shrink-0 border-l border-zinc-800 bg-zinc-900/50 flex flex-col">
          <div className="shrink-0 flex items-center justify-between px-3 pt-3 pb-1">
            <span className="text-xs font-medium text-zinc-400">History</span>
            <button
              onClick={() => setShowHistory(false)}
              className="p-1 text-zinc-500 hover:text-zinc-300 rounded transition"
              title="Collapse history"
            >
              <History className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3 pt-1">
            <FrictionHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} />
          </div>
        </div>
      ) : (
        <div className="shrink-0 border-l border-zinc-800 bg-zinc-900/50 flex flex-col items-center pt-3 px-1">
          <button
            onClick={() => setShowHistory(true)}
            className="p-1.5 text-zinc-500 hover:text-zinc-300 rounded transition"
            title="Show history"
          >
            <History className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}

const MODEL_PRESETS = [
  "anthropic/claude-sonnet-4-5",
  "anthropic/claude-haiku-4-5",
  "openai/gpt-4.1",
  "openai/gpt-4.1-mini",
  "google/gemini-2.5-flash",
];

function ModelCombobox({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <div className="flex">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setOpen(true)}
          placeholder="anthropic/claude-sonnet-4-5"
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-amber-600 pr-8"
        />
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="absolute right-0 inset-y-0 px-2 flex items-center text-zinc-500 hover:text-zinc-300"
        >
          <ChevronDown className="w-3.5 h-3.5" />
        </button>
      </div>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <ul className="absolute z-20 mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl overflow-hidden">
            {MODEL_PRESETS.map((preset) => (
              <li key={preset}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(preset);
                    setOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-700 transition ${
                    value === preset ? "text-amber-400" : "text-zinc-200"
                  }`}
                >
                  {preset}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function LLMConfigForm({
  fetchWithToken,
  onConfigured,
}: {
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onConfigured: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("anthropic/claude-sonnet-4-5");
  const [submitting, setSubmitting] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!apiKey.trim()) return;
    setSubmitting(true);
    setConfigError(null);
    try {
      const res = await fetchWithToken("/api/llm/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: apiKey.trim(), model: model.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      onConfigured();
    } catch (err) {
      setConfigError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, [apiKey, model, fetchWithToken, onConfigured]);

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-zinc-400 mb-1">API Key</label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-ant-..."
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-amber-600"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-zinc-400 mb-1">Model</label>
        <ModelCombobox value={model} onChange={setModel} />
      </div>
      {configError && (
        <div className="px-3 py-2 bg-rose-900/20 border border-rose-800/50 rounded-lg text-xs text-rose-300">
          {configError}
        </div>
      )}
      <button
        onClick={handleSubmit}
        disabled={!apiKey.trim() || submitting}
        className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
        Connect
      </button>
    </div>
  );
}

function LLMConfigSection({
  llmStatus,
  fetchWithToken,
  onConfigured,
}: {
  llmStatus: LLMStatus | null;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onConfigured: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const isConnected = llmStatus?.available === true;
  const isMock = llmStatus?.backend_id === "mock";

  // Mock backend (test mode) needs no config UI
  if (isMock) return null;

  if (isConnected && !showForm) {
    return (
      <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-800/60 border border-zinc-700/50 rounded-lg mb-6">
        <span className="text-xs text-zinc-400">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 align-middle" />
          {llmStatus.backend_id} / {llmStatus.model}
        </span>
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition"
        >
          <Pencil className="w-3 h-3" />
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-5 mb-6">
      <h4 className="text-sm font-semibold text-zinc-200 mb-3">
        {isConnected ? "Update LLM Configuration" : "Configure LLM Backend"}
      </h4>
      <p className="text-xs text-zinc-400 mb-4">
        Provide an API key and model to enable LLM-powered friction analysis.
      </p>
      <LLMConfigForm
        fetchWithToken={fetchWithToken}
        onConfigured={() => {
          setShowForm(false);
          onConfigured();
        }}
      />
      {isConnected && (
        <button
          onClick={() => setShowForm(false)}
          className="mt-2 text-xs text-zinc-500 hover:text-zinc-300 transition"
        >
          Cancel
        </button>
      )}
    </div>
  );
}

function EmptyState({
  checkedCount,
  error,
  onRun,
  llmStatus,
  fetchWithToken,
  onLlmConfigured,
}: {
  checkedCount: number;
  error: string | null;
  onRun: () => void;
  llmStatus: LLMStatus | null;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onLlmConfigured: () => void;
}) {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center max-w-md">
        <Sparkles className="w-12 h-12 mx-auto mb-4 text-amber-400/50" />
        <h3 className="text-lg font-semibold text-zinc-200 mb-2">
          Friction Analysis
        </h3>
        <p className="text-sm text-zinc-400 mb-6">
          Select sessions and run analysis to find friction events and CLAUDE.md suggestions.
        </p>
        <LLMConfigSection
          llmStatus={llmStatus}
          fetchWithToken={fetchWithToken}
          onConfigured={onLlmConfigured}
        />
        {error && (
          <div className="mb-4 px-4 py-2.5 bg-rose-900/20 border border-rose-800/50 rounded-lg text-xs text-rose-300">
            {error}
          </div>
        )}
        <Tip text="Check sessions in the sidebar to get started">
          <button
            onClick={onRun}
            disabled={checkedCount === 0}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play className="w-4 h-4" />
            Analyze {checkedCount > 0 ? `${checkedCount} session${checkedCount !== 1 ? "s" : ""}` : "sessions"}
          </button>
        </Tip>
      </div>
    </div>
  );
}

function ResultHeader({
  result,
  onRerun,
  onNew,
}: {
  result: FrictionAnalysisResult;
  onRerun: () => void;
  onNew: () => void;
}) {
  const eventCount = result.events.length;
  const sessionCount = result.session_ids.length;

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Activity className="w-6 h-6 text-amber-400" />
        <div>
          <h2 className="text-xl font-bold text-zinc-100">
            Friction Analysis
          </h2>
          <p className="text-sm text-zinc-400">
            {eventCount} event{eventCount !== 1 ? "s" : ""} across {sessionCount} session{sessionCount !== 1 ? "s" : ""}
            {result.sessions_skipped.length > 0 && (
              <span className="text-zinc-500">
                {" "}&middot; {result.sessions_skipped.length} skipped
              </span>
            )}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onNew}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
        >
          <Plus className="w-3 h-3" />
          New
        </button>
        <button
          onClick={onRerun}
          className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
        >
          Re-run
        </button>
      </div>
    </div>
  );
}

function SummarySection({
  summary,
  topMitigation,
}: {
  summary: string;
  topMitigation: string;
}) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-5 space-y-3">
      <p className="text-sm text-zinc-200 leading-relaxed">{summary}</p>
      <Tip text="The single highest-impact action to reduce friction across all analyzed sessions.">
        <div className="flex items-start gap-3 bg-amber-900/15 border border-amber-700/30 rounded-lg px-5 py-4">
          <Zap className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-300 mb-1">Top recommendation</p>
            <p className="text-sm text-zinc-200">{topMitigation}</p>
          </div>
        </div>
      </Tip>
    </div>
  );
}

function ModeSummarySection({ modes }: { modes: ModeSummary[] }) {
  const maxCost = Math.max(...modes.map((m) => m.total_estimated_cost.wasted_steps), 1);

  return (
    <div>
      <SectionTitle icon={<BookOpen className="w-5 h-5 text-cyan-400" />} title="Mode Summary" />
      <div className="grid grid-cols-2 gap-3">
        {modes.map((mode) => (
          <ModeCard key={mode.mode} mode={mode} maxCost={maxCost} />
        ))}
      </div>
    </div>
  );
}

function ModeCard({ mode, maxCost }: { mode: ModeSummary; maxCost: number }) {
  const barWidth = (mode.total_estimated_cost.wasted_steps / maxCost) * 100;

  return (
    <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-4 space-y-3">
      {/* Mode name + severity */}
      <div className="flex items-center justify-between">
        <ModeBadge mode={mode.mode} />
        <SeverityBadge severity={Math.round(mode.avg_severity)} />
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-3">
        <Tip text="Number of friction events with this mode">
          <span className="flex items-center gap-1 text-xs text-zinc-300">
            <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />
            {mode.count} event{mode.count !== 1 ? "s" : ""}
          </span>
        </Tip>
        <Tip text="Number of distinct sessions affected by this mode">
          <span className="flex items-center gap-1 text-xs text-zinc-300">
            <Hash className="w-3.5 h-3.5 text-violet-400" />
            {mode.affected_sessions} session{mode.affected_sessions !== 1 ? "s" : ""}
          </span>
        </Tip>
      </div>

      {/* Cost breakdown — same style as EventCard */}
      <CostRow
        steps={mode.total_estimated_cost.wasted_steps}
        time={mode.total_estimated_cost.wasted_time_seconds}
        tokens={mode.total_estimated_cost.wasted_tokens}
      />

      {/* Relative wasted-steps bar */}
      <Tip text={`Relative wasted steps: ${mode.total_estimated_cost.wasted_steps} steps (${Math.round(barWidth)}% of the worst mode)`}>
        <div className="h-1 w-full bg-zinc-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-amber-500/60 rounded-full transition-all"
            style={{ width: `${barWidth}%` }}
          />
        </div>
      </Tip>
    </div>
  );
}

function SuggestionsSection({
  suggestions,
}: {
  suggestions: ClaudeMdSuggestion[];
}) {
  return (
    <div>
      <SectionTitle icon={<FileText className="w-5 h-5 text-violet-400" />} title="CLAUDE.md Suggestions" />
      <div className="space-y-2">
        {suggestions.map((s, i) => (
          <SuggestionCard key={i} suggestion={s} />
        ))}
      </div>
    </div>
  );
}

function SuggestionCard({ suggestion }: { suggestion: ClaudeMdSuggestion }) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-lg p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-sm font-medium bg-cyan-900/30 border border-cyan-700/30 text-cyan-300 mb-2">
            {suggestion.section}
          </span>
          <p className="text-sm text-zinc-100 font-mono leading-relaxed">
            &ldquo;{suggestion.rule}&rdquo;
          </p>
          <p className="text-sm text-zinc-400 mt-2 leading-relaxed">
            {suggestion.rationale}
          </p>
        </div>
        <CopyButton text={suggestion.rule} className="shrink-0 mt-1" />
      </div>
    </div>
  );
}

function EventsSection({
  events,
  sessionIds,
}: {
  events: FrictionEvent[];
  sessionIds: string[];
}) {
  const eventsBySession = new Map<string, FrictionEvent[]>();
  for (const sid of sessionIds) {
    eventsBySession.set(sid, []);
  }
  for (const event of events) {
    const list = eventsBySession.get(event.ref.session_id) ?? [];
    list.push(event);
    eventsBySession.set(event.ref.session_id, list);
  }

  return (
    <div>
      <SectionTitle icon={<AlertTriangle className="w-5 h-5 text-amber-400" />} title="Friction Events" />
      <div className="space-y-3">
        {[...eventsBySession.entries()]
          .filter(([, evts]) => evts.length > 0)
          .map(([sid, evts]) => (
            <SessionEventGroup key={sid} sessionId={sid} events={evts} />
          ))}
      </div>
    </div>
  );
}

function SessionEventGroup({
  sessionId,
  events,
}: {
  sessionId: string;
  events: FrictionEvent[];
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="border border-zinc-700/60 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 bg-zinc-800/50 hover:bg-zinc-800 transition text-left"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-zinc-400 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-zinc-400 shrink-0" />
        )}
        <span className="text-sm font-medium text-zinc-200">
          Session {sessionId.slice(0, SESSION_ID_SHORT)}
        </span>
        <span className="text-xs text-zinc-500">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </span>
      </button>
      {expanded && (
        <div className="divide-y divide-zinc-700/60">
          {events.map((event) => (
            <EventCard key={event.event_id} event={event} />
          ))}
        </div>
      )}
    </div>
  );
}

function EventCard({ event }: { event: FrictionEvent }) {
  const [expanded, setExpanded] = useState(false);

  const handleGoToStep = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const url = `${window.location.origin}?session=${event.ref.session_id}&step=${event.ref.start_step_id}`;
      window.open(url, "_blank");
    },
    [event.ref.session_id, event.ref.start_step_id]
  );

  return (
    <div className="px-4 py-3.5">
      {/* Header row */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left"
      >
        <div className="flex items-start gap-2">
          <div className="mt-0.5 shrink-0">
            {expanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            {/* Tags row: severity + mode + jump */}
            <div className="flex items-center gap-2 mb-1.5">
              <SeverityBadge severity={event.severity} />
              <ModeBadge mode={event.mode} />
              <button
                onClick={handleGoToStep}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-sm text-zinc-400 hover:text-cyan-400 hover:bg-cyan-900/20 rounded transition"
                title="Open this step in a new tab"
              >
                <ArrowUpRight className="w-4 h-4" />
                <span>Jump</span>
              </button>
            </div>
            {/* Description */}
            <p className={`text-sm text-zinc-200 leading-relaxed ${expanded ? "" : "line-clamp-2"}`}>
              {event.description}
            </p>
            {/* Cost row — shared component */}
            <div className="mt-2">
              <CostRow
                steps={event.estimated_cost.wasted_steps}
                time={event.estimated_cost.wasted_time_seconds}
                tokens={event.estimated_cost.wasted_tokens}
                stepCount={event.step_ids.length}
                toolCallId={event.ref.tool_call_id}
              />
            </div>
          </div>
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="ml-6 mt-3 pt-3 border-t border-zinc-700/40 divide-y divide-zinc-700/40">
          <div className="pb-3">
            <DetailBlock label="Evidence" icon={<Search className="w-4 h-4 text-sky-400" />}>
              <p className="text-zinc-200 text-sm leading-relaxed">{event.evidence}</p>
            </DetailBlock>
          </div>
          <div className="py-3">
            <DetailBlock label="Root Cause" icon={<Target className="w-4 h-4 text-rose-400" />}>
              <p className="text-zinc-200 text-sm leading-relaxed">{event.root_cause}</p>
            </DetailBlock>
          </div>
          {event.mitigations.length > 0 && (
            <div className="py-3">
              <DetailBlock label="Mitigations" icon={<Shield className="w-4 h-4 text-emerald-400" />}>
                <ul className="space-y-1.5">
                  {event.mitigations.map((m, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-zinc-200">
                      <span className="text-emerald-400 mt-0.5 shrink-0">&#8226;</span>
                      <span className="leading-relaxed">{m}</span>
                    </li>
                  ))}
                </ul>
              </DetailBlock>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CostRow({
  steps,
  time,
  tokens,
  stepCount,
  toolCallId,
}: {
  steps: number;
  time: number | null;
  tokens: number | null;
  stepCount?: number;
  toolCallId?: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Tip text="Estimated steps consumed by friction (retries, rework, exploration)">
        <span className="inline-flex items-center gap-1 text-xs text-zinc-300">
          <Footprints className="w-3.5 h-3.5 text-rose-400" />
          {steps} step{steps !== 1 ? "s" : ""} wasted
        </span>
      </Tip>
      {time != null && (
        <Tip text="Estimated wall-clock time lost">
          <span className="inline-flex items-center gap-1 text-xs text-zinc-300">
            <Clock className="w-3.5 h-3.5 text-sky-400" />
            {formatDuration(time)}
          </span>
        </Tip>
      )}
      {tokens != null && (
        <Tip text="Estimated tokens spent on friction (input + output)">
          <span className="inline-flex items-center gap-1 text-xs text-zinc-300">
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            {formatTokens(tokens)}
          </span>
        </Tip>
      )}
      {toolCallId && (
        <Tip text="Specific tool call involved in this friction">
          <span className="inline-flex items-center gap-1 text-xs text-violet-300">
            <Wrench className="w-3.5 h-3.5 text-violet-400" />
            {toolCallId.slice(0, SESSION_ID_MEDIUM)}
          </span>
        </Tip>
      )}
      {stepCount != null && (
        <Tip text="Number of trajectory steps where this friction manifests">
          <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
            <Search className="w-3.5 h-3.5" />
            {stepCount} step{stepCount !== 1 ? "s" : ""}
          </span>
        </Tip>
      )}
    </div>
  );
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      {icon}
      <h3 className="text-base font-semibold text-zinc-100">{title}</h3>
    </div>
  );
}

function DetailBlock({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <p className="text-sm font-semibold text-zinc-100">{label}</p>
      </div>
      {children}
    </div>
  );
}

function ModeBadge({ mode }: { mode: string }) {
  return (
    <Tip text={`Friction mode: "${mode}" — a pattern of wasted effort identified by the LLM`}>
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-sm font-medium bg-amber-900/30 border border-amber-700/30 text-amber-300">
        <Target className="w-4 h-4" />
        {mode}
      </span>
    </Tip>
  );
}

function SeverityBadge({ severity }: { severity: number }) {
  const colorClass = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS[3];
  const label = SEVERITY_LABELS[severity] ?? "Unknown";
  return (
    <Tip text={SEVERITY_DESCRIPTIONS[severity] ?? "Impact severity rating"}>
      <span className={`inline-flex items-center justify-center gap-1.5 min-w-[6.5rem] px-2.5 py-1 rounded text-sm font-medium border shrink-0 ${colorClass}`}>
        <Shield className="w-4 h-4" />
        {label}
      </span>
    </Tip>
  );
}

function AnalysisMeta({ result }: { result: FrictionAnalysisResult }) {
  const computedDate = new Date(result.computed_at);
  const timeStr = isNaN(computedDate.getTime())
    ? result.computed_at
    : computedDate.toLocaleString();

  return (
    <Tip text="Inference backend, model, and estimated API cost for this analysis run">
      <div className="border-t border-zinc-800 pt-4 text-xs text-zinc-500 flex items-center justify-between">
        <span>
          {result.backend_id}/{result.model}
          {result.cost_usd != null && <> &middot; {formatCost(result.cost_usd)}</>}
        </span>
        <span>{timeStr}</span>
      </div>
    </Tip>
  );
}

function Tip({
  text,
  children,
}: {
  text: string;
  children: React.ReactNode;
}) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const ref = useRef<HTMLDivElement>(null);

  const handleEnter = useCallback(() => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    setPos({ x: rect.left + rect.width / 2, y: rect.top });
    setShow(true);
  }, []);

  return (
    <div
      ref={ref}
      className="inline-flex"
      onMouseEnter={handleEnter}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show &&
        createPortal(
          <div
            style={{ left: pos.x, top: pos.y }}
            className="fixed -translate-x-1/2 -translate-y-full -mt-2 z-[9999] px-3.5 py-2 rounded-lg bg-zinc-950 border border-zinc-700 text-xs text-zinc-300 w-max max-w-md whitespace-normal shadow-xl pointer-events-none leading-relaxed"
          >
            {text}
          </div>,
          document.body,
        )}
    </div>
  );
}
