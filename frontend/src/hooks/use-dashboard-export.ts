import { useCallback, useMemo, useState } from "react";
import { useAppContext } from "../app";
import { dashboardClient, type DashboardFilters } from "../api/dashboard";

type ExportFormat = "csv" | "json";

interface UseDashboardExportResult {
  exporting: ExportFormat | null;
  exportDashboard: (format: ExportFormat, filters?: DashboardFilters) => Promise<void>;
}

/** Trigger a dashboard export download and track the in-flight format so the
 * UI can show a spinner on the right button.
 */
export function useDashboardExport(): UseDashboardExportResult {
  const { fetchWithToken } = useAppContext();
  const api = useMemo(() => dashboardClient(fetchWithToken), [fetchWithToken]);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);

  const exportDashboard = useCallback(
    async (format: ExportFormat, filters?: DashboardFilters) => {
      setExporting(format);
      try {
        const blob = await api.export(format, filters);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `vibelens-dashboard.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (err) {
        console.error("Export failed:", err);
      } finally {
        setExporting(null);
      }
    },
    [api],
  );

  return { exporting, exportDashboard };
}
