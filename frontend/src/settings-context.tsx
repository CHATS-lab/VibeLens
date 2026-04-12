import { createContext, useContext, useState, useEffect } from "react";
import type { ReactNode } from "react";

export type FontScale = "90%" | "100%" | "110%" | "120%" | "130%";
export type ThemePreference = "system" | "light" | "dark";

const FONT_SCALE_OPTIONS: FontScale[] = ["90%", "100%", "110%", "120%", "130%"];
const THEME_OPTIONS: ThemePreference[] = ["system", "light", "dark"];

const STORAGE_KEY = "vibelens-settings";
const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

interface PersistedSettings {
  fontScale?: string;
  theme?: string;
}

interface SettingsValue {
  fontScale: FontScale;
  setFontScale: (scale: FontScale) => void;
  fontScaleOptions: FontScale[];
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  themeOptions: ThemePreference[];
}

const SettingsContext = createContext<SettingsValue>({
  fontScale: "100%",
  setFontScale: () => {},
  fontScaleOptions: FONT_SCALE_OPTIONS,
  theme: "system",
  setTheme: () => {},
  themeOptions: THEME_OPTIONS,
});

export function useSettings(): SettingsValue {
  return useContext(SettingsContext);
}

function loadPersistedSettings(): PersistedSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as PersistedSettings;
  } catch {
    return {};
  }
}

function loadPersistedScale(): FontScale {
  const parsed = loadPersistedSettings();
  if (parsed.fontScale && FONT_SCALE_OPTIONS.includes(parsed.fontScale as FontScale)) {
    return parsed.fontScale as FontScale;
  }
  return "100%";
}

function loadPersistedTheme(): ThemePreference {
  const parsed = loadPersistedSettings();
  if (parsed.theme && THEME_OPTIONS.includes(parsed.theme as ThemePreference)) {
    return parsed.theme as ThemePreference;
  }
  return "system";
}

function persistSettings(fontScale: FontScale, theme: ThemePreference): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ fontScale, theme }));
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [fontScale, setFontScaleState] = useState<FontScale>(loadPersistedScale);
  const [theme, setThemeState] = useState<ThemePreference>(loadPersistedTheme);

  const setFontScale = (scale: FontScale) => {
    setFontScaleState(scale);
    persistSettings(scale, theme);
  };

  const setTheme = (newTheme: ThemePreference) => {
    setThemeState(newTheme);
    persistSettings(fontScale, newTheme);
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

  // Apply dark/light class on <html> based on theme preference and OS setting
  useEffect(() => {
    const mediaQuery = window.matchMedia(DARK_MEDIA_QUERY);

    function applyTheme() {
      const isDark =
        theme === "dark" || (theme === "system" && mediaQuery.matches);
      document.documentElement.classList.toggle("dark", isDark);
    }

    applyTheme();

    if (theme === "system") {
      mediaQuery.addEventListener("change", applyTheme);
      return () => mediaQuery.removeEventListener("change", applyTheme);
    }
  }, [theme]);

  return (
    <SettingsContext.Provider
      value={{
        fontScale,
        setFontScale,
        fontScaleOptions: FONT_SCALE_OPTIONS,
        theme,
        setTheme,
        themeOptions: THEME_OPTIONS,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}
