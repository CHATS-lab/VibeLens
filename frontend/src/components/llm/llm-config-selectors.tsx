import { ChevronDown } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import type { CliBackendModels, LiteLLMPreset } from "../../types";
import {
  ACCENT_STYLES,
  BACKEND_OPTIONS,
  CLI_BACKENDS,
  PricingLine,
  formatPrice,
  type AccentColor,
} from "./llm-config-constants";

export function ModelCombobox({
  value,
  onChange,
  presets,
  accentColor = "cyan",
}: {
  value: string;
  onChange: (v: string) => void;
  presets: LiteLLMPreset[];
  accentColor?: AccentColor;
}) {
  const [open, setOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  // Tracks user-typed search. Null means "not actively searching" so the
  // dropdown shows all presets; a string (possibly empty) means the user
  // is filtering by that substring.
  const [searchQuery, setSearchQuery] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const accent = ACCENT_STYLES[accentColor];
  const selectedPreset = presets.find((p) => p.name === value);
  const filteredPresets =
    searchQuery === null
      ? presets
      : presets.filter((p) =>
          p.name.toLowerCase().includes(searchQuery.toLowerCase()),
        );

  // Flip dropdown upward when insufficient space below (matches max-h-72)
  const DROPDOWN_HEIGHT = 288;
  const updateDropDirection = useCallback(() => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    setDropUp(spaceBelow < DROPDOWN_HEIGHT && rect.top > spaceBelow);
  }, []);

  return (
    <div>
      <div className="relative" ref={containerRef}>
        <div className="flex">
          <input
            type="text"
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              setSearchQuery(e.target.value);
              updateDropDirection();
              setOpen(true);
            }}
            onFocus={() => {
              setSearchQuery(null);
              updateDropDirection();
              setOpen(true);
            }}
            placeholder="Type or select a model..."
            className={`w-full px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary placeholder-zinc-500 focus:outline-none ${accent.focus} pr-8`}
          />
          <button
            type="button"
            onClick={() => {
              setSearchQuery(null);
              updateDropDirection();
              setOpen((v) => !v);
            }}
            className="absolute right-0 inset-y-0 px-2 flex items-center text-dimmed hover:text-secondary hover:bg-control/30 rounded-r-lg transition"
          >
            <ChevronDown className={`w-3.5 h-3.5 transition ${open ? "rotate-180" : ""}`} />
          </button>
        </div>
        {open && filteredPresets.length > 0 && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <ul
              className={`absolute z-20 w-full max-h-72 overflow-y-auto bg-control border border-card rounded-lg shadow-xl ${
                dropUp ? "bottom-full mb-1" : "top-full mt-1"
              }`}
            >
              {filteredPresets.map((preset) => (
                <li key={preset.name}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(preset.name);
                      setSearchQuery(null);
                      setOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-control-hover transition flex justify-between items-center gap-3 ${
                      value === preset.name ? accent.selected : "text-secondary"
                    }`}
                  >
                    <span className="truncate">{preset.name}</span>
                    {preset.input_per_mtok != null && (
                      <span className="text-dimmed text-xs shrink-0">
                        ${formatPrice(preset.input_per_mtok)} / ${formatPrice(preset.output_per_mtok!)}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      {selectedPreset?.input_per_mtok != null && (
        <PricingLine
          inputPrice={selectedPreset.input_per_mtok}
          outputPrice={selectedPreset.output_per_mtok!}
        />
      )}
    </div>
  );
}

export function CliModelSelector({
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
      <p className="text-xs text-dimmed">
        No model selection available for this backend.
      </p>
    );
  }

  if (meta.supports_freeform) {
    return (
      <div className="relative">
        <div className="flex">
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={() => setOpen(true)}
            placeholder={meta.default_model ?? "model name"}
            className={`w-full px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary placeholder-zinc-500 focus:outline-none ${accent.focus} pr-8`}
          />
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="absolute right-0 inset-y-0 px-2 flex items-center text-dimmed hover:text-secondary hover:bg-control/30 rounded-r-lg transition"
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
        </div>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-control border border-card rounded-lg shadow-xl">
              {meta.models.map((m) => (
                <li key={m.name}>
                  <button
                    type="button"
                    onClick={() => { onChange(m.name); setOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-control-hover transition ${
                      value === m.name ? accent.selected : "text-secondary"
                    }`}
                  >
                    {m.name}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`w-full flex items-center justify-between px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary focus:outline-none ${accent.focus} transition`}
      >
        <span>{value || meta.default_model || "Select model"}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-dimmed transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-control border border-card rounded-lg shadow-xl">
            {meta.models.map((m) => (
              <li key={m.name}>
                <button
                  type="button"
                  onClick={() => { onChange(m.name); setOpen(false); }}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-control-hover transition ${
                    value === m.name ? accent.selected : "text-secondary"
                  }`}
                >
                  {m.name}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function BackendDropdown({
  value,
  onChange,
  cliModels,
  accentColor = "cyan",
}: {
  value: string;
  onChange: (v: string) => void;
  cliModels: Record<string, CliBackendModels>;
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
        className={`w-full flex items-center justify-between px-3 py-2 bg-control border border-card rounded-lg text-sm text-secondary focus:outline-none ${accent.focus} transition`}
      >
        <span>{selected?.label ?? value}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-dimmed transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-control border border-card rounded-lg shadow-xl">
            {BACKEND_OPTIONS.map((opt) => {
              const isInstalled =
                CLI_BACKENDS.has(opt.value) && cliModels[opt.value]?.available === true;
              return (
                <li key={opt.value}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(opt.value);
                      setOpen(false);
                    }}
                    className={`w-full flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-control-hover transition ${
                      value === opt.value ? accent.selected : "text-secondary"
                    }`}
                  >
                    <span>{opt.label}</span>
                    {isInstalled && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-2 py-0.5">
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        installed
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
