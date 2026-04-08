import { useCallback, useState } from "react";
import { useAppContext } from "../app";

/**
 * Hook that guards write actions in demo mode by showing the install dialog
 * instead of executing the action. In non-demo mode, actions pass through.
 */
export function useDemoGuard() {
  const { appMode } = useAppContext();
  const isDemo = appMode === "demo";
  const [showInstallDialog, setShowInstallDialog] = useState(false);

  const guardAction = useCallback(
    (action: () => void) => {
      if (isDemo) {
        setShowInstallDialog(true);
      } else {
        action();
      }
    },
    [isDemo],
  );

  return { isDemo, showInstallDialog, setShowInstallDialog, guardAction };
}
