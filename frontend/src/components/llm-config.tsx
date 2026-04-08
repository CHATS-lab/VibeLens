import {
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  Pencil,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CliBackendModels, LLMStatus } from "../types";

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
  { value: "claude-cli", label: "Claude Code" },
  { value: "codex-cli", label: "Codex" },
  { value: "gemini-cli", label: "Gemini CLI" },
  { value: "cursor-cli", label: "Cursor" },
  { value: "kimi-cli", label: "Kimi" },
  { value: "openclaw-cli", label: "OpenClaw" },
  { value: "opencode-cli", label: "OpenCode" },
  { value: "aider-cli", label: "Aider" },
  { value: "amp-cli", label: "Amp" },
  { value: "disabled", label: "Disabled" },
];

const CLI_BACKENDS = new Set([
  "claude-cli",
  "codex-cli",
  "gemini-cli",
  "cursor-cli",
  "kimi-cli",
  "openclaw-cli",
  "opencode-cli",
  "aider-cli",
  "amp-cli",
]);

type AccentColor = "amber" | "teal" | "cyan";

const ACCENT_STYLES: Record<AccentColor, { focus: string; button: string; selected: string }> = {
  amber: {
    focus: "focus:border-amber-600",
    button: "bg-amber-600 hover:bg-amber-500",
    selected: "text-amber-400",
  },
  teal: {
    focus: "focus:border-teal-600",
    button: "bg-teal-600 hover:bg-teal-500",
    selected: "text-teal-400",
  },
  cyan: {
    focus: "focus:border-cyan-600",
    button: "bg-cyan-600 hover:bg-cyan-500",
    selected: "text-cyan-400",
  },
};

function formatPrice(price: number): string {
  return price < 0.01 ? price.toFixed(3) : price.toFixed(2);
}

function PricingLine({ inputPrice, outputPrice }: { inputPrice: number; outputPrice: number }) {
  return (
    <p className="text-xs text-zinc-500 mt-1">
      ${formatPrice(inputPrice)} / ${formatPrice(outputPrice)} per MTok (in / out)
    </p>
  );
}

function ModelCombobox({
  value,
  onChange,
  accentColor = "cyan",
}: {
  value: string;
  onChange: (v: string) => void;
  accentColor?: AccentColor;
}) {
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const accent = ACCENT_STYLES[accentColor];
  const query = value.toLowerCase();
  const filteredPresets = MODEL_PRESETS.filter((p) => p.toLowerCase().includes(query));

  // Flip dropdown upward when insufficient space below
  const DROPDOWN_HEIGHT = 192;
  const updateDropDirection = useCallback(() => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    setDropUp(spaceBelow < DROPDOWN_HEIGHT && rect.top > spaceBelow);
  }, []);

  return (
    <div className="relative" ref={containerRef}>
      <div className="flex">
        <input
          type="text"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            updateDropDirection();
            setOpen(true);
          }}
          onFocus={() => {
            updateDropDirection();
            setOpen(true);
          }}
          placeholder="Type or select a model..."
          className={`w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none ${accent.focus} pr-8`}
        />
        <button
          type="button"
          onClick={() => {
            updateDropDirection();
            setOpen((v) => !v);
          }}
          className="absolute right-0 inset-y-0 px-2 flex items-center text-zinc-500 hover:text-zinc-300"
        >
          <ChevronDown className={`w-3.5 h-3.5 transition ${open ? "rotate-180" : ""}`} />
        </button>
      </div>
      {open && filteredPresets.length > 0 && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <ul
            className={`absolute z-20 w-full max-h-48 overflow-y-auto bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl ${
              dropUp ? "bottom-full mb-1" : "top-full mt-1"
            }`}
          >
            {filteredPresets.map((preset) => (
              <li key={preset}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(preset);
                    setOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-700 transition ${
                    value === preset ? accent.selected : "text-zinc-200"
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

function CliModelSelector({
  backendId,
  value,
  onChange,
  cliModels,
  accentColor = "cyan",
}: {
  backendId: string;
  value: string;
  onChange: (v: string) => void;
  cliModels: Record<string, CliBackendModels>;
  accentColor?: AccentColor;
}) {
  const [open, setOpen] = useState(false);
  const accent = ACCENT_STYLES[accentColor];
  const meta = cliModels[backendId];

  if (!meta || meta.models.length === 0) {
    return (
      <p className="text-xs text-zinc-500">
        No model selection available for this backend.
      </p>
    );
  }

  const selectedModel = meta.models.find((m) => m.name === value);

  if (meta.supports_freeform) {
    return (
      <div>
        <div className="relative">
          <div className="flex">
            <input
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onFocus={() => setOpen(true)}
              placeholder={meta.default_model ?? "model name"}
              className={`w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none ${accent.focus} pr-8`}
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
              <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl">
                {meta.models.map((m) => (
                  <li key={m.name}>
                    <button
                      type="button"
                      onClick={() => { onChange(m.name); setOpen(false); }}
                      className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-700 transition flex justify-between ${
                        value === m.name ? accent.selected : "text-zinc-200"
                      }`}
                    >
                      <span>{m.name}</span>
                      {m.input_per_mtok != null && (
                        <span className="text-zinc-500 text-xs">${formatPrice(m.input_per_mtok)} / ${formatPrice(m.output_per_mtok!)}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
        {selectedModel?.input_per_mtok != null && (
          <PricingLine inputPrice={selectedModel.input_per_mtok} outputPrice={selectedModel.output_per_mtok!} />
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={`w-full flex items-center justify-between px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none ${accent.focus} transition`}
        >
          <span>{value || meta.default_model || "Select model"}</span>
          <ChevronDown className={`w-3.5 h-3.5 text-zinc-500 transition ${open ? "rotate-180" : ""}`} />
        </button>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl">
              {meta.models.map((m) => (
                <li key={m.name}>
                  <button
                    type="button"
                    onClick={() => { onChange(m.name); setOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-700 transition flex justify-between ${
                      value === m.name ? accent.selected : "text-zinc-200"
                    }`}
                  >
                    <span>{m.name}</span>
                    {m.input_per_mtok != null && (
                      <span className="text-zinc-500 text-xs">${formatPrice(m.input_per_mtok)} / ${formatPrice(m.output_per_mtok!)}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      {selectedModel?.input_per_mtok != null && (
        <PricingLine inputPrice={selectedModel.input_per_mtok} outputPrice={selectedModel.output_per_mtok!} />
      )}
    </div>
  );
}

function BackendDropdown({
  value,
  onChange,
  accentColor = "cyan",
}: {
  value: string;
  onChange: (v: string) => void;
  accentColor?: AccentColor;
}) {
  const [open, setOpen] = useState(false);
  const accent = ACCENT_STYLES[accentColor];
  const selected = BACKEND_OPTIONS.find((o) => o.value === value);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none ${accent.focus} transition`}
      >
        <span>{selected?.label ?? value}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-zinc-500 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl">
            {BACKEND_OPTIONS.map((opt) => (
              <li key={opt.value}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(opt.value);
                    setOpen(false);
                  }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-700 transition ${
                    value === opt.value ? accent.selected : "text-zinc-200"
                  }`}
                >
                  {opt.label}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

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
  const [maxTokens, setMaxTokens] = useState(llmStatus?.max_tokens ?? 4096);
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
        payload.max_tokens = maxTokens;
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
        <label className="block text-xs font-medium text-zinc-300 mb-1">Backend</label>
        <BackendDropdown value={backend} onChange={setBackend} accentColor={accentColor} />
      </div>

      {!isCliBackend && backend !== "disabled" && (
        <div>
          <label className="block text-xs font-medium text-zinc-300 mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={llmStatus?.api_key_masked ? `Keep existing (${llmStatus.api_key_masked})` : "sk-ant-..."}
            className={`w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none ${accent.focus}`}
          />
          {llmStatus?.api_key_masked && !apiKey && (
            <p className="mt-1 text-xs text-zinc-400">
              Key configured: {llmStatus.api_key_masked}. Leave empty to keep it.
            </p>
          )}
        </div>
      )}

      {!isCliBackend && backend !== "disabled" && (
        <div>
          <label className="block text-xs font-medium text-zinc-300 mb-1">Model</label>
          <ModelCombobox value={model} onChange={setModel} accentColor={accentColor} />
        </div>
      )}

      {isCliBackend && hasCliModels && (
        <div>
          <label className="block text-xs font-medium text-zinc-300 mb-1">Model</label>
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
        <p className="text-xs text-zinc-400">
          Uses your local {BACKEND_OPTIONS.find((o) => o.value === backend)?.label ?? backend} installation. No model selection available.
        </p>
      )}

      {!isCliBackend && backend !== "disabled" && (
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition"
        >
          {showAdvanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Advanced
        </button>
      )}

      {showAdvanced && !isCliBackend && backend !== "disabled" && (
        <div className="space-y-3 pl-3 border-l-2 border-zinc-700/50">
          <div>
            <label className="block text-xs font-medium text-zinc-300 mb-1">
              Base URL <span className="text-zinc-500">(auto-resolved if empty)</span>
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.anthropic.com"
              className={`w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none ${accent.focus}`}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-300 mb-1">Timeout (s)</label>
              <input
                type="number"
                value={timeout}
                onChange={(e) => setTimeout_(parseInt(e.target.value) || 120)}
                min={10}
                max={600}
                className={`w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none ${accent.focus}`}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-300 mb-1">Max Tokens</label>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
                min={256}
                max={32768}
                className={`w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none ${accent.focus}`}
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
      <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-800/60 border border-zinc-700/50 rounded-lg mb-6">
        <div>
          <span className="text-xs text-zinc-400">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 align-middle" />
            {llmStatus.backend_id} / {llmStatus.model}
          </span>
          {pricing && (
            <span className="text-xs text-zinc-500 ml-2">
              (${formatPrice(pricing.input_per_mtok)} / ${formatPrice(pricing.output_per_mtok)} per MTok)
            </span>
          )}
        </div>
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
          className="mt-2 text-xs text-zinc-500 hover:text-zinc-300 transition"
        >
          Cancel
        </button>
      )}
    </div>
  );
}
