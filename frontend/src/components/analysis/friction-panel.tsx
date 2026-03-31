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
  Footprints,
  Hash,
  History,
  Layers,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Play,
  Plus,
  Shield,
  Sparkles,
  Target,
  Wrench,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAppContext } from "../../app";
import type {
  FrictionAnalysisResult,
  FrictionEstimate,
  FrictionEvent,
  LLMStatus,
  Mitigation,
  TypeSummary,
} from "../../types";
import { formatCost, formatDuration, formatTokens } from "../../utils";
import { SEVERITY_COLORS, SESSION_ID_SHORT, SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH } from "../../styles";
import { CopyButton } from "../copy-button";
import { LoadingSpinner } from "../loading-spinner";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../modal";
import { FrictionHistory } from "./friction-history";

const SEVERITY_LABELS: Record<number, string> = {
  1: "Minor",
  2: "Low",
  3: "Moderate",
  4: "High",
  5: "Critical",
};

const SEVERITY_DESCRIPTIONS: Record<number, string> = {
  1: "Minor — Small user correction, agent fixes immediately",
  2: "Low — User re-explains once, agent gets it on second try",
  3: "Moderate — Multiple corrections or visible frustration",
  4: "High — User takes over manually or reverts agent work",
  5: "Critical — User abandons task or loses work",
};

const ACTION_KEYWORD_COLORS: [RegExp, string][] = [
  [/claude\.?md/i, "bg-violet-500/25 border-violet-400/50 text-violet-200"],
  [/test/i, "bg-emerald-500/25 border-emerald-400/50 text-emerald-200"],
  [/skill/i, "bg-cyan-500/25 border-cyan-400/50 text-cyan-200"],
  [/lint|eslint|ruff/i, "bg-amber-500/25 border-amber-400/50 text-amber-200"],
  [/workflow|ci|pipeline/i, "bg-rose-500/25 border-rose-400/50 text-rose-200"],
];

const DEFAULT_ACTION_COLOR = "bg-teal-500/20 border-teal-400/40 text-teal-200";

// Sidebar width constants imported from styles.ts

function _actionColor(action: string): string {
  for (const [pattern, color] of ACTION_KEYWORD_COLORS) {
    if (pattern.test(action)) return color;
  }
  return DEFAULT_ACTION_COLOR;
}

interface FrictionPanelProps {
  checkedIds: Set<string>;
}

export function FrictionPanel({ checkedIds }: FrictionPanelProps) {
  const { fetchWithToken } = useAppContext();
  const [result, setResult] = useState<FrictionAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [showSidebar, setShowSidebar] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const draggingRef = useRef(false);

  const handleDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      draggingRef.current = true;
      const startX = e.clientX;
      const startWidth = sidebarWidth;

      const onMouseMove = (ev: MouseEvent) => {
        if (!draggingRef.current) return;
        const delta = startX - ev.clientX;
        const newWidth = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, startWidth + delta));
        setSidebarWidth(newWidth);
      };
      const onMouseUp = () => {
        draggingRef.current = false;
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [sidebarWidth],
  );

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

  const [estimate, setEstimate] = useState<FrictionEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);

  const handleRequestAnalysis = useCallback(async () => {
    if (checkedIds.size === 0) return;
    setEstimating(true);
    setError(null);
    try {
      const res = await fetchWithToken("/api/analysis/friction/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: [...checkedIds] }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      setEstimate(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setEstimating(false);
    }
  }, [checkedIds, fetchWithToken]);

  const handleConfirmAnalysis = useCallback(async () => {
    setEstimate(null);
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
  }, []);

  const handleNewAnalysis = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const sidebar = useMemo(() => (
    <>
      {showSidebar && (
        <>
          {/* Drag handle */}
          <div
            onMouseDown={handleDragStart}
            className="w-1 shrink-0 cursor-col-resize bg-zinc-800 hover:bg-zinc-600 transition-colors"
          />
          {/* Sidebar content */}
          <div
            className="shrink-0 border-l border-zinc-800 bg-zinc-900/50 flex flex-col"
            style={{ width: sidebarWidth }}
          >
            <div className="shrink-0 flex items-center justify-between px-3 pt-3 pb-1">
              <div className="flex items-center gap-1.5">
                <History className="w-3.5 h-3.5 text-zinc-500" />
                <span className="text-xs font-medium text-zinc-400">History</span>
              </div>
              <button
                onClick={() => setShowSidebar(false)}
                className="p-0.5 text-zinc-500 hover:text-zinc-300 transition"
                title="Hide history"
              >
                <PanelRightClose className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 pt-1">
              <FrictionHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} />
            </div>
          </div>
        </>
      )}
      {!showSidebar && (
        <div className="shrink-0 border-l border-zinc-800 bg-zinc-900/50 flex flex-col items-center pt-3 px-1">
          <button
            onClick={() => setShowSidebar(true)}
            className="p-1 text-zinc-500 hover:text-zinc-300 transition"
            title="Show history"
          >
            <PanelRightOpen className="w-4 h-4" />
          </button>
        </div>
      )}
    </>
  ), [showSidebar, sidebarWidth, handleDragStart, handleHistorySelect, historyRefresh]);

  const estimateDialog = estimate && (
    <CostEstimateDialog
      estimate={estimate}
      sessionCount={checkedIds.size}
      onConfirm={handleConfirmAnalysis}
      onCancel={() => setEstimate(null)}
    />
  );

  if (loading || estimating) {
    return (
      <LoadingSpinner
        label={
          estimating
            ? `Estimating cost for ${checkedIds.size} session${checkedIds.size !== 1 ? "s" : ""}`
            : `Analyzing ${checkedIds.size} session${checkedIds.size !== 1 ? "s" : ""} for friction`
        }
        sublabel={estimating ? "Preparing batches…" : "This may take a moment"}
      />
    );
  }

  if (!result) {
    return (
      <div className="h-full flex">
        <div className="flex-1">
          <EmptyState
            checkedCount={checkedIds.size}
            error={error}
            onRun={handleRequestAnalysis}
            llmStatus={llmStatus}
            fetchWithToken={fetchWithToken}
            onLlmConfigured={refreshLlmStatus}
          />
        </div>
        {sidebar}
        {estimateDialog}
      </div>
    );
  }

  return (
    <div className="h-full flex">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
          <ResultHeader result={result} onNew={handleNewAnalysis} />
          <SummarySection
            summary={result.summary}
            topMitigations={result.top_mitigations ?? []}
            crossBatchPatterns={result.cross_batch_patterns}
          />
          {result.type_summary.length > 0 && (
            <TypeSummarySection types={result.type_summary} />
          )}
          <EventsSection events={result.events} />
          <AnalysisMeta result={result} />
        </div>
      </div>
      {sidebar}
    </div>
  );
}

const MODEL_PRESETS = [
  "anthropic/claude-haiku-4-5",
  "anthropic/claude-sonnet-4-5",
  "openai/gpt-4.1",
  "openai/gpt-4.1-mini",
  "google/gemini-2.5-flash",
  "deepseek/deepseek-chat",
  "openrouter/anthropic/claude-sonnet-4-5",
];

const BACKEND_OPTIONS = [
  { value: "litellm", label: "LiteLLM (recommended)" },
  { value: "claude-cli", label: "Claude CLI" },
  { value: "codex-cli", label: "Codex CLI" },
  { value: "disabled", label: "Disabled" },
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
          placeholder="anthropic/claude-haiku-4-5"
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
  llmStatus,
}: {
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onConfigured: () => void;
  llmStatus: LLMStatus | null;
}) {
  const [backend, setBackend] = useState(llmStatus?.backend_id === "mock" ? "litellm" : llmStatus?.backend_id ?? "litellm");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(llmStatus?.model ?? "anthropic/claude-haiku-4-5");
  const [baseUrl, setBaseUrl] = useState(llmStatus?.base_url ?? "");
  const [timeout, setTimeout_] = useState(llmStatus?.timeout ?? 120);
  const [maxTokens, setMaxTokens] = useState(llmStatus?.max_tokens ?? 4096);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);

  const isCliBackend = backend === "claude-cli" || backend === "codex-cli";
  const hasExistingKey = !!llmStatus?.api_key_masked;

  const handleSubmit = useCallback(async () => {
    if (!isCliBackend && !apiKey.trim() && !hasExistingKey) return;
    setSubmitting(true);
    setConfigError(null);
    try {
      const payload: Record<string, unknown> = {
        backend: backend.trim(),
        api_key: apiKey.trim(),
        model: model.trim(),
        timeout,
        max_tokens: maxTokens,
      };
      if (baseUrl.trim()) payload.base_url = baseUrl.trim();
      const res = await fetchWithToken("/api/llm/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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
  }, [backend, apiKey, model, baseUrl, timeout, maxTokens, isCliBackend, hasExistingKey, fetchWithToken, onConfigured]);

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-zinc-400 mb-1">Backend</label>
        <select
          value={backend}
          onChange={(e) => setBackend(e.target.value)}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-amber-600"
        >
          {BACKEND_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {!isCliBackend && backend !== "disabled" && (
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={llmStatus?.api_key_masked ? `Keep existing (${llmStatus.api_key_masked})` : "sk-ant-..."}
            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-amber-600"
          />
          {llmStatus?.api_key_masked && !apiKey && (
            <p className="mt-1 text-xs text-zinc-500">
              Key configured: {llmStatus.api_key_masked}. Leave empty to keep it.
            </p>
          )}
        </div>
      )}

      {backend !== "disabled" && (
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1">Model</label>
          <ModelCombobox value={model} onChange={setModel} />
        </div>
      )}

      {backend !== "disabled" && (
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition"
        >
          {showAdvanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Advanced
        </button>
      )}

      {showAdvanced && backend !== "disabled" && (
        <div className="space-y-3 pl-3 border-l-2 border-zinc-700/50">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">
              Base URL <span className="text-zinc-600">(auto-resolved if empty)</span>
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.anthropic.com"
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-amber-600"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Timeout (s)</label>
              <input
                type="number"
                value={timeout}
                onChange={(e) => setTimeout_(parseInt(e.target.value) || 120)}
                min={10}
                max={600}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-amber-600"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Max Tokens</label>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
                min={256}
                max={32768}
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-amber-600"
              />
            </div>
          </div>
        </div>
      )}

      {configError && (
        <div className="px-3 py-2 bg-rose-900/20 border border-rose-800/50 rounded-lg text-xs text-rose-300">
          {configError}
        </div>
      )}
      <button
        onClick={handleSubmit}
        disabled={(!isCliBackend && backend !== "disabled" && !apiKey.trim() && !hasExistingKey) || submitting}
        className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
        {backend === "disabled" ? "Disable" : "Connect"}
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
        llmStatus={llmStatus}
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
        <h3 className="text-lg font-semibold text-zinc-200 mb-1">
          Productivity Tips
        </h3>
        <p className="text-xs text-zinc-500 mb-3">
          Identify patterns that slow you down and get concrete improvements.
        </p>
        <p className="text-sm text-zinc-400 mb-6">
          Select sessions and run analysis to detect wasted effort, recurring mistakes, and generate actionable mitigations.
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
  onNew,
}: {
  result: FrictionAnalysisResult;
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
            {result.title || "Friction Analysis"}
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
      <button
        onClick={onNew}
        className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
      >
        <Plus className="w-3 h-3" />
        New
      </button>
    </div>
  );
}

function SummarySection({
  summary,
  topMitigations,
  crossBatchPatterns,
}: {
  summary: string;
  topMitigations: Mitigation[];
  crossBatchPatterns?: string[];
}) {
  const hasPatterns = crossBatchPatterns && crossBatchPatterns.length > 0;

  return (
    <div className="space-y-4">
      <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-5 space-y-3">
        <p className="text-sm text-zinc-200 leading-relaxed">{summary}</p>
        {hasPatterns && (
          <div className="border-t border-zinc-700/40 pt-3 space-y-2">
            {crossBatchPatterns.map((pattern, i) => (
              <div key={i} className="flex items-start gap-2.5">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400/60 shrink-0" />
                <p className="text-sm text-zinc-200 leading-relaxed">{pattern}</p>
              </div>
            ))}
          </div>
        )}
      </div>
      {topMitigations.length > 0 && (
        <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-5 space-y-3">
          <Tip text="Highest-impact actions to reduce friction across all analyzed sessions.">
            <div className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-amber-400" />
              <h3 className="text-base font-semibold text-zinc-100">
                Top Recommendation{topMitigations.length > 1 ? "s" : ""}
              </h3>
            </div>
          </Tip>
          <div className="space-y-2">
            {topMitigations.map((m, i) => (
              <MitigationCard key={i} mitigation={m} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TypeSummarySection({ types }: { types: TypeSummary[] }) {
  const maxCost = Math.max(...types.map((t) => t.total_estimated_cost.affected_steps), 1);

  return (
    <div>
      <SectionTitle icon={<BookOpen className="w-5 h-5 text-cyan-400" />} title="Friction Types" />
      <div className="grid grid-cols-2 gap-3">
        {types.map((type) => (
          <TypeCard key={type.friction_type} type={type} maxCost={maxCost} />
        ))}
      </div>
    </div>
  );
}

function TypeCard({ type, maxCost }: { type: TypeSummary; maxCost: number }) {
  const barWidth = (type.total_estimated_cost.affected_steps / maxCost) * 100;

  return (
    <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <TypeBadge type={type.friction_type} />
        <SeverityBadge severity={Math.round(type.avg_severity)} />
      </div>

      {type.description && (
        <p className="text-xs text-zinc-400 leading-relaxed">{type.description}</p>
      )}

      <div className="flex items-center gap-3">
        <Tip text="Number of friction events of this type">
          <span className="flex items-center gap-1 text-xs text-zinc-300">
            <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />
            {type.count} event{type.count !== 1 ? "s" : ""}
          </span>
        </Tip>
        <Tip text="Number of distinct sessions affected">
          <span className="flex items-center gap-1 text-xs text-zinc-300">
            <Hash className="w-3.5 h-3.5 text-violet-400" />
            {type.affected_sessions} session{type.affected_sessions !== 1 ? "s" : ""}
          </span>
        </Tip>
      </div>

      <CostRow
        steps={type.total_estimated_cost.affected_steps}
        time={type.total_estimated_cost.affected_time_seconds}
        tokens={type.total_estimated_cost.affected_tokens}
      />

      <Tip text={`Relative affected steps: ${type.total_estimated_cost.affected_steps} (${Math.round(barWidth)}% of worst type)`}>
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

function EventsSection({
  events,
}: {
  events: FrictionEvent[];
}) {
  // Group events by project_path instead of session
  const eventsByProject = new Map<string, FrictionEvent[]>();
  for (const event of events) {
    const project = _extractProjectName(event);
    const list = eventsByProject.get(project) ?? [];
    list.push(event);
    eventsByProject.set(project, list);
  }

  return (
    <div>
      <SectionTitle icon={<AlertTriangle className="w-5 h-5 text-amber-400" />} title="Friction Events" />
      <div className="space-y-3">
        {[...eventsByProject.entries()]
          .sort(([, a], [, b]) => {
            const maxA = Math.max(...a.map((e) => e.severity));
            const maxB = Math.max(...b.map((e) => e.severity));
            return maxB - maxA;
          })
          .map(([project, evts], groupIndex) => (
            <ProjectEventGroup key={project} projectName={project} events={evts} isFirstGroup={groupIndex === 0} />
          ))}
      </div>
    </div>
  );
}

function _extractProjectName(event: FrictionEvent): string {
  if (!event.project_path) {
    return `Session ${event.span_ref.session_id.slice(0, 8)}`;
  }
  const parts = event.project_path.replace(/\/$/, "").split("/");
  return parts[parts.length - 1] || event.project_path;
}

function ProjectEventGroup({
  projectName,
  events,
  isFirstGroup = false,
}: {
  projectName: string;
  events: FrictionEvent[];
  isFirstGroup?: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const sortedEvents = [...events].sort((a, b) => b.severity - a.severity);
  const sessionCount = new Set(events.map((e) => e.span_ref.session_id)).size;

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
          {projectName}
        </span>
        <span className="text-xs text-zinc-500">
          {events.length} event{events.length !== 1 ? "s" : ""}
          {sessionCount > 1 && ` · ${sessionCount} sessions`}
        </span>
      </button>
      {expanded && (
        <div className="divide-y divide-zinc-700/60">
          {sortedEvents.map((event, i) => (
            <EventCard key={event.friction_id} event={event} defaultExpanded={isFirstGroup && i === 0} />
          ))}
        </div>
      )}
    </div>
  );
}

function EventCard({ event, defaultExpanded = false }: { event: FrictionEvent; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const handleGoToStep = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const url = `${window.location.origin}?session=${event.span_ref.session_id}&step=${event.span_ref.start_step_id}`;
      window.open(url, "_blank");
    },
    [event.span_ref.session_id, event.span_ref.start_step_id]
  );

  return (
    <div className="px-4 py-3.5">
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
            {/* Tags row: severity + type + session + jump */}
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <SeverityBadge severity={event.severity} />
              <TypeBadge type={event.friction_type} />
              <Tip text={`Session: ${event.span_ref.session_id}`}>
                <span className="text-xs text-zinc-500 font-mono">
                  {event.span_ref.session_id.slice(0, SESSION_ID_SHORT)}
                </span>
              </Tip>
              <button
                onClick={handleGoToStep}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-sm text-zinc-400 hover:text-cyan-400 hover:bg-cyan-900/20 rounded transition"
                title="Open this step in a new tab"
              >
                <ArrowUpRight className="w-4 h-4" />
                <span>Jump</span>
              </button>
            </div>
            {/* User intention */}
            <p className="text-sm text-zinc-200 leading-relaxed font-medium">
              {event.user_intention}
            </p>
            {/* Friction detail */}
            {event.friction_detail && (
              <p className={`text-sm text-zinc-400 mt-1 leading-relaxed ${expanded ? "" : "line-clamp-2"}`}>
                {event.friction_detail}
              </p>
            )}
            {/* Cost row */}
            <div className="mt-2">
              <CostRow
                steps={event.estimated_cost.affected_steps}
                time={event.estimated_cost.affected_time_seconds}
                tokens={event.estimated_cost.affected_tokens}
              />
            </div>
          </div>
        </div>
      </button>

      {/* Expanded: mitigations */}
      {expanded && event.mitigations.length > 0 && (
        <div className="ml-6 mt-3 pt-3 border-t border-zinc-700/40">
          <div className="flex items-center gap-2 mb-2">
            <Wrench className="w-4 h-4 text-emerald-400" />
            <p className="text-sm font-semibold text-zinc-100">Mitigations</p>
          </div>
          <div className="space-y-2">
            {event.mitigations.map((m, i) => (
              <MitigationCard key={i} mitigation={m} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MitigationCard({ mitigation }: { mitigation: Mitigation }) {
  const actionLabel = mitigation.action
    || (mitigation.action_type
      ? `${mitigation.action_type.replace(/_/g, " ")}${mitigation.target ? `: ${mitigation.target}` : ""}`
      : "Action");
  const colorClass = _actionColor(actionLabel);

  return (
    <div className="bg-zinc-900/60 border border-zinc-700/40 rounded-lg p-3">
      <div className="mb-2">
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-sm font-semibold border ${colorClass}`}>
          <Wrench className="w-3.5 h-3.5" />
          {actionLabel}
        </span>
      </div>
      <div className="flex items-start gap-2">
        <p className="text-sm text-zinc-200 font-mono leading-relaxed flex-1">
          {mitigation.content}
        </p>
        <CopyButton text={mitigation.content} className="shrink-0 mt-0.5" />
      </div>
    </div>
  );
}

function CostRow({
  steps,
  time,
  tokens,
}: {
  steps: number;
  time: number | null;
  tokens: number | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Tip text="Steps affected by this friction">
        <span className="inline-flex items-center gap-1 text-xs text-zinc-300">
          <Footprints className="w-3.5 h-3.5 text-rose-400" />
          {steps} step{steps !== 1 ? "s" : ""} affected
        </span>
      </Tip>
      {time != null && (
        <Tip text="Time span of the friction">
          <span className="inline-flex items-center gap-1 text-xs text-zinc-300">
            <Clock className="w-3.5 h-3.5 text-sky-400" />
            {formatDuration(time)}
          </span>
        </Tip>
      )}
      {tokens != null && (
        <Tip text="Tokens consumed in the friction span">
          <span className="inline-flex items-center gap-1 text-xs text-zinc-300">
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            {formatTokens(tokens)}
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

function TypeBadge({ type }: { type: string }) {
  return (
    <Tip text={`Friction type: "${type}" — a pattern of user dissatisfaction`}>
      <span className="inline-flex items-center gap-1.5 min-w-[10rem] px-2.5 py-1 rounded text-sm font-medium bg-amber-900/30 border border-amber-700/30 text-amber-300">
        <Target className="w-4 h-4 shrink-0" />
        {type}
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
  const computedDate = new Date(result.created_at);
  const dateStr = isNaN(computedDate.getTime())
    ? result.created_at
    : computedDate.toLocaleDateString();
  const timeStr = isNaN(computedDate.getTime())
    ? ""
    : computedDate.toLocaleTimeString();

  return (
    <Tip text="Inference backend, model, and estimated API cost for this analysis run">
      <div className="border-t border-zinc-800 pt-4 text-xs text-zinc-500 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{result.backend_id}/{result.model}</span>
          {result.cost_usd != null && (
            <span className="border-l border-zinc-700 pl-2">
              {formatCost(result.cost_usd)}
            </span>
          )}
          {result.batch_count > 1 && (
            <span className="border-l border-zinc-700 pl-2">
              {result.batch_count} batches
            </span>
          )}
        </div>
        <span className="shrink-0">{dateStr} {timeStr}</span>
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

function CostEstimateDialog({
  estimate,
  sessionCount,
  onConfirm,
  onCancel,
}: {
  estimate: FrictionEstimate;
  sessionCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal onClose={onCancel} maxWidth="max-w-md">
      <ModalHeader title="Confirm Analysis" onClose={onCancel} />
      <ModalBody>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <InfoRow icon={<Layers className="w-3.5 h-3.5 text-violet-400" />} label="Sessions" value={String(sessionCount)} />
            <InfoRow icon={<BarChart3 className="w-3.5 h-3.5 text-cyan-400" />} label="Batches" value={String(estimate.batch_count)} />
            <InfoRow icon={<Hash className="w-3.5 h-3.5 text-zinc-400" />} label="Input tokens" value={formatTokens(estimate.total_input_tokens)} />
            <InfoRow icon={<Hash className="w-3.5 h-3.5 text-zinc-400" />} label="Output budget" value={formatTokens(estimate.total_output_tokens_budget)} />
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Model: {estimate.model}</span>
          </div>
          <div className="bg-amber-900/20 border border-amber-700/30 rounded-lg px-4 py-3">
            <div className="flex items-center gap-2">
              <Coins className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-medium text-amber-200">
                Estimated cost: {estimate.formatted_cost}
              </span>
            </div>
            {!estimate.pricing_found && (
              <p className="mt-1 text-xs text-amber-400/70">
                Model not in pricing table — actual cost may vary.
              </p>
            )}
          </div>
        </div>
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium rounded-md transition"
        >
          <Play className="w-3 h-3" />
          Run Analysis
        </button>
      </ModalFooter>
    </Modal>
  );
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-zinc-800/50 rounded-lg">
      {icon}
      <div className="flex flex-col">
        <span className="text-[10px] text-zinc-500">{label}</span>
        <span className="text-xs text-zinc-200">{value}</span>
      </div>
    </div>
  );
}
