import { useEffect, useState } from "react";
import { useExtensionsClient } from "../../../../app";
import { errorMessage } from "../../../../utils";

interface CollectionExportDialogProps {
  collectionName: string;
  onClose: () => void;
}

export function CollectionExportDialog({
  collectionName,
  onClose,
}: CollectionExportDialogProps) {
  const client = useExtensionsClient();
  const [payload, setPayload] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.collections
      .export(collectionName)
      .then((data) => setPayload(JSON.stringify(data, null, 2)))
      .catch((err) => setError(errorMessage(err)));
  }, [client, collectionName]);

  function handleDownload() {
    if (!payload) return;
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${collectionName}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-base p-6 rounded-lg max-w-2xl w-full mx-4 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold">Export &quot;{collectionName}&quot;</h3>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        {payload && (
          <pre className="p-3 bg-elevated rounded text-xs overflow-auto max-h-96">
            {payload}
          </pre>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-secondary">
            Close
          </button>
          <button
            onClick={handleDownload}
            disabled={!payload}
            className="px-3 py-1.5 text-xs rounded-md bg-accent-teal text-white disabled:opacity-50"
          >
            Download JSON
          </button>
        </div>
      </div>
    </div>
  );
}
