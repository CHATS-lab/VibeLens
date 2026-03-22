import { createContext, useContext, useState, useEffect } from "react";
import type { ReactNode } from "react";

export type FontScale = "90%" | "100%" | "110%" | "120%" | "130%";

const FONT_SCALE_OPTIONS: FontScale[] = ["90%", "100%", "110%", "120%", "130%"];

const STORAGE_KEY = "vibelens-settings";

interface SettingsValue {
  fontScale: FontScale;
  setFontScale: (scale: FontScale) => void;
  fontScaleOptions: FontScale[];
}

const SettingsContext = createContext<SettingsValue>({
  fontScale: "100%",
  setFontScale: () => {},
  fontScaleOptions: FONT_SCALE_OPTIONS,
});

export function useSettings(): SettingsValue {
  return useContext(SettingsContext);
}

function loadPersistedScale(): FontScale {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return "100%";
    const parsed = JSON.parse(raw) as { fontScale?: string };
    if (parsed.fontScale && FONT_SCALE_OPTIONS.includes(parsed.fontScale as FontScale)) {
      return parsed.fontScale as FontScale;
    }
  } catch {
    // Ignore corrupt storage
  }
  return "100%";
}

function persistScale(scale: FontScale): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ fontScale: scale }));
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [fontScale, setFontScaleState] = useState<FontScale>(loadPersistedScale);

  const setFontScale = (scale: FontScale) => {
    setFontScaleState(scale);
    persistScale(scale);
  };

  // Apply CSS zoom on #root and adjust dimensions so content fills the viewport
  useEffect(() => {
    const root = document.getElementById("root");
    if (!root) return;
    const zoomValue = parseInt(fontScale) / 100;
    root.style.zoom = String(zoomValue);
    root.style.height = `${100 / zoomValue}vh`;
    root.style.width = `${100 / zoomValue}vw`;
  }, [fontScale]);

  return (
    <SettingsContext.Provider
      value={{ fontScale, setFontScale, fontScaleOptions: FONT_SCALE_OPTIONS }}
    >
      {children}
    </SettingsContext.Provider>
  );
}
