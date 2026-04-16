import {
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  Pencil,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { CliBackendModels, LLMStatus } from "../../types";
import {
  ACCENT_STYLES,
  BACKEND_OPTIONS,
  CLI_BACKENDS,
  formatPrice,
  type AccentColor,
} from "./llm-config-constants";
import {
  BackendDropdown,
  CliModelSelector,
  ModelCombobox,
} from "./llm-config-selectors";

export type { AccentColor };

export function LLMConfigForm({
  fetchWithToken,
  onConfigured,
  llmStatus,
  accentColor = "cyan",
}: {
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onConfigured: () => void;
  llmStatus: LLMStatus | null;
  accentColor?: AccentColor;
}) {
  const [backend, setBackend] = useState(llmStatus?.backend_id === "mock" ? "litellm" : llmStatus?.backend_id ?? "litellm");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(llmStatus?.model ?? "");
  const [cliModel, setCliModel] = useState("");
  const [baseUrl, setBaseUrl] = useState(llmStatus?.base_url ?? "");
  const [timeout, setTimeout_] = useState(llmStatus?.timeout ?? 120);
  const [maxTokens, setMaxTokens] = useState(llmStatus?.max_output_tokens ?? 4096);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [cliModels, setCliModels] = useState<Record<string, CliBackendModels>>({});

  const accent = ACCENT_STYLES[accentColor];
  const isCliBackend = CLI_BACKENDS.has(backend);
  const hasExistingKey = !!llmStatus?.api_key_masked;

  useEffect(() => {
    fetchWithToken("/api/llm/cli-models")
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data) setCliModels(data);
      })
      .catch(() => {});
  }, [fetchWithToken]);

  // Auto-select default model when switching to a CLI backend
  useEffect(() => {
    if (!isCliBackend) return;
    const meta = cliModels[backend];
    if (meta?.default_model) {
      setCliModel(meta.default_model);
    } else {
      setCliModel("");
    }
  }, [backend, cliModels, isCliBackend]);

  const handleSubmit = useCallback(async () => {
    if (!isCliBackend && backend !== "disabled" && !apiKey.trim() && !hasExistingKey) return;
    setSubmitting(true);
    setConfigError(null);
    try {
      const payload: Record<string, unknown> = { backend: backend.trim() };
      if (isCliBackend) {
        if (cliModel.trim()) {
          payload.model = cliModel.trim();
        }
      } else if (backend !== "disabled") {
        payload.api_key = apiKey.trim();
        payload.model = model.trim();
        payload.timeout = timeout;
        payload.max_output_tokens = maxTokens;
        if (baseUrl.trim()) payload.base_url = baseUrl.trim();
      }
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
  }, [backend, apiKey, model, cliModel, baseUrl, timeout, maxTokens, isCliBackend, hasExistingKey, fetchWithToken, onConfigured]);

  const cliMeta = cliModels[backend];
  const hasCliModels = cliMeta && cliMeta.models.length > 0;

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-secondary mb-1">Backend</label>
        <BackendDropdown value={backend} onChange={setBackend} accentColor={accentColor} />
      </div>

      {!isCliBackend && backend !== "disabled" && (
        <div>
          <label className="block text-xs font-medium text-secondary mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={llmStatus?.api_key_masked ? `Keep existing (${llmStatus.api_key_masked})` : "sk-ant-..."}
            className={`w-full px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary placeholder-zinc-500 focus:outline-none ${accent.focus}`}
          />
          {llmStatus?.api_key_masked && !apiKey && (
            <p className="mt-1 text-xs text-muted">
              Key configured: {llmStatus.api_key_masked}. Leave empty to keep it.
            </p>
          )}
        </div>
      )}

      {!isCliBackend && backend !== "disabled" && (
        <div>
          <label className="block text-xs font-medium text-secondary mb-1">Model</label>
          <ModelCombobox value={model} onChange={setModel} accentColor={accentColor} />
        </div>
      )}

      {isCliBackend && hasCliModels && (
        <div>
          <label className="block text-xs font-medium text-secondary mb-1">Model</label>
          <CliModelSelector
            backendId={backend}
            value={cliModel}
            onChange={setCliModel}
            cliModels={cliModels}
            accentColor={accentColor}
          />
        </div>
      )}

      {isCliBackend && !hasCliModels && (
        <p className="text-xs text-muted">
          Uses your local {BACKEND_OPTIONS.find((o) => o.value === backend)?.label ?? backend} installation. No model selection available.
        </p>
      )}

      {!isCliBackend && backend !== "disabled" && (
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1 text-xs text-muted hover:text-secondary hover:bg-control/30 rounded px-1 -mx-1 transition"
        >
          {showAdvanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Advanced
        </button>
      )}

      {showAdvanced && !isCliBackend && backend !== "disabled" && (
        <div className="space-y-3 pl-3 border-l-2 border-card">
          <div>
            <label className="block text-xs font-medium text-secondary mb-1">
              Base URL <span className="text-dimmed">(auto-resolved if empty)</span>
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.anthropic.com"
              className={`w-full px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary placeholder-zinc-500 focus:outline-none ${accent.focus}`}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-secondary mb-1">Timeout (s)</label>
              <input
                type="number"
                value={timeout}
                onChange={(e) => setTimeout_(parseInt(e.target.value) || 120)}
                min={10}
                max={600}
                className={`w-full px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary focus:outline-none ${accent.focus}`}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-secondary mb-1">Max Tokens</label>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
                min={256}
                max={32768}
                className={`w-full px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary focus:outline-none ${accent.focus}`}
              />
            </div>
          </div>
        </div>
      )}

      {configError && (
        <div className="px-3 py-2 bg-accent-rose-subtle border border-rose-200 dark:border-rose-800/40 rounded-lg text-xs text-accent-rose">
          {configError}
        </div>
      )}
      <button
        onClick={handleSubmit}
        disabled={(!isCliBackend && backend !== "disabled" && !apiKey.trim() && !hasExistingKey) || submitting}
        className={`inline-flex items-center gap-2 px-4 py-2 ${accent.button} text-white text-sm font-medium rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed`}
      >
        {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
        {backend === "disabled" ? "Disable" : "Connect"}
      </button>
    </div>
  );
}

export function LLMConfigSection({
  llmStatus,
  fetchWithToken,
  onConfigured,
  accentColor = "cyan",
}: {
  llmStatus: LLMStatus | null;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onConfigured: () => void;
  accentColor?: AccentColor;
}) {
  const [showForm, setShowForm] = useState(false);
  const isConnected = llmStatus?.available === true;
  const isMock = llmStatus?.backend_id === "mock";

  if (isMock) return null;

  if (isConnected && !showForm) {
    const pricing = llmStatus.pricing;
    return (
      <div className="flex items-center justify-between px-4 py-2.5 bg-control/60 border border-card rounded-lg mb-6">
        <div>
          <span className="text-xs text-muted">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 align-middle" />
            {llmStatus.backend_id} / {llmStatus.model}
          </span>
          {pricing && (
            <span className="text-xs text-dimmed ml-2">
              (${formatPrice(pricing.input_per_mtok)} / ${formatPrice(pricing.output_per_mtok)} per MTok)
            </span>
          )}
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-1 text-xs text-dimmed hover:text-secondary hover:bg-control/30 rounded px-1 -mx-1 transition"
        >
          <Pencil className="w-3 h-3" />
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="bg-panel/80 border border-card rounded-xl p-5 mb-6">
      <h4 className="text-sm font-semibold text-secondary mb-3">
        {isConnected ? "Update LLM Configuration" : "Configure LLM Backend"}
      </h4>
      <p className="text-xs text-muted mb-4">
        Provide an API key and model to enable LLM-powered analysis.
      </p>
      <LLMConfigForm
        fetchWithToken={fetchWithToken}
        llmStatus={llmStatus}
        accentColor={accentColor}
        onConfigured={() => {
          setShowForm(false);
          onConfigured();
        }}
      />
      {isConnected && (
        <button
          onClick={() => setShowForm(false)}
          className="mt-2 text-xs text-dimmed hover:text-secondary hover:bg-control/30 rounded px-1 -mx-1 transition"
        >
          Cancel
        </button>
      )}
    </div>
  );
}
