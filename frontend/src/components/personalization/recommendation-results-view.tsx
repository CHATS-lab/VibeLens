import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { PersonalizationResult, RankedRecommendationItem } from "../../types";
import { RecommendationCard } from "./recommendation-card";

interface RecommendationResultsViewProps {
  analysisId: string;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
}

function ProfilePills({ profile }: { profile: NonNullable<PersonalizationResult["user_profile"]> }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {profile.domains.map((d) => (
        <span key={d} className="px-2 py-0.5 text-xs rounded-full bg-accent-cyan-subtle text-accent-cyan">
          {d}
        </span>
      ))}
      {profile.languages.map((l) => (
        <span key={l} className="px-2 py-0.5 text-xs rounded-full bg-accent-emerald-subtle text-accent-emerald">
          {l}
        </span>
      ))}
      {profile.frameworks.map((f) => (
        <span key={f} className="px-2 py-0.5 text-xs rounded-full bg-accent-violet-subtle text-accent-violet">
          {f}
        </span>
      ))}
    </div>
  );
}

function MetadataLine({ result }: { result: PersonalizationResult }) {
  const costStr = result.final_metrics?.total_cost_usd != null ? `$${result.final_metrics.total_cost_usd.toFixed(2)}` : "";
  const durationStr = result.final_metrics?.duration ? `${result.final_metrics.duration}s` : "";
  const metaParts = [
    `${result.session_ids.length} sessions analyzed`,
    durationStr,
    result.model,
    costStr,
  ].filter(Boolean);
  return <p className="text-xs text-dimmed">{metaParts.join(" \u00b7 ")}</p>;
}

export function RecommendationView({ analysisId, fetchWithToken }: RecommendationResultsViewProps) {
  const [result, setResult] = useState<PersonalizationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchWithToken(`/api/recommendation/${analysisId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load recommendation: ${res.status}`);
        return res.json();
      })
      .then((data) => setResult(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [analysisId, fetchWithToken]);

  const handleInstall = useCallback((rec: RankedRecommendationItem) => {
    if (rec.item.install_command) {
      navigator.clipboard.writeText(rec.item.install_command);
    }
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-accent-cyan" />
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-sm text-dimmed">{error ?? "No result found"}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="border-b border-default px-6 py-4 space-y-2 shrink-0">
        <h1 className="text-xl font-semibold text-primary">{result.title}</h1>
        {result.user_profile && <ProfilePills profile={result.user_profile} />}
        <MetadataLine result={result} />
      </div>

      {/* Card list */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {result.recommendations.length === 0 ? (
          <p className="text-sm text-dimmed text-center py-8">
            No recommendations found.
          </p>
        ) : (
          result.recommendations.map((rec, idx) => (
            <RecommendationCard
              key={rec.item.extension_id}
              recommendation={rec}
              rank={idx + 1}
              onInstall={handleInstall}
            />
          ))
        )}
      </div>
    </div>
  );
}
