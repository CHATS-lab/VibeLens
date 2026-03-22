import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app";
import { SettingsProvider } from "./settings-context";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SettingsProvider>
      <App />
    </SettingsProvider>
  </StrictMode>
);
