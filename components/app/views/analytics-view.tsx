import type { AnalyticsSnapshot } from "@/components/app/types";

function formatGen(amount: number): string {
  return amount.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatHours(hours: number | null): string {
  if (hours == null) return "—";
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 48) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

// Same stat-tile anatomy as dashboard-view.tsx's own three tiles — label
// above, big font-display number below — kept as a small local component
// here since analytics needs five of them and dashboard-view.tsx's aren't
// exported for reuse.
function StatTile({
  label,
  value,
  unit,
  accentClass,
}: {
  label: string;
  value: string;
  unit?: string;
  accentClass?: string;
}) {
  return (
    <div className="rounded-[14px] border border-border-1 bg-surface-1 p-5">
      <div className="text-xs uppercase tracking-wide text-fg-meta">{label}</div>
      <div className={`mt-1.5 font-display text-[26px] font-bold ${accentClass ?? ""}`}>
        {value} {unit && <span className="text-sm font-normal text-fg-meta">{unit}</span>}
      </div>
    </div>
  );
}

export function AnalyticsView({ analytics }: { analytics: AnalyticsSnapshot }) {
  const rankedLeaderboard = analytics.validatorLeaderboard.filter((v) => v.casesJudged > 0);

  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="mb-1 font-display text-[30px] font-bold">Analytics</div>
      <div className="mb-7 mt-1 text-[15px] text-fg-dim-2">
        Value locked, dispute throughput, and validator accuracy across Nuance —
        computed live from real escrow, dispute, and consensus history.
      </div>

      <div className="mb-9 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          label="Total Value Locked"
          value={formatGen(analytics.tvlOpenEscrowsGen)}
          unit="GEN"
        />
        <StatTile
          label="Open Escrows"
          value={String(analytics.openEscrowCount)}
        />
        <StatTile
          label="Prediction Market Volume"
          value={formatGen(analytics.predictionMarketVolumeGen)}
          unit={`GEN · ${analytics.predictionMarketCount} markets`}
        />
        <StatTile
          label="Dispute Resolution (Median)"
          value={formatHours(analytics.disputeResolutionMedianHours)}
        />
        <StatTile
          label="Disputes Resolved"
          value={String(analytics.resolvedDisputeCount)}
        />
      </div>

      <div className="mb-3 text-lg font-semibold">Validator Accuracy Leaderboard</div>
      {rankedLeaderboard.length === 0 ? (
        <div className="rounded-[14px] border border-dashed border-border-4 bg-surface-1/50 p-6 text-center text-sm text-fg-meta">
          No completed consensus jobs yet — the leaderboard fills in as validators judge real cases.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-[14px] border border-border-1 bg-surface-1">
          <table className="w-full min-w-[480px] text-left text-sm">
            <thead>
              <tr className="border-b border-border-1 text-xs uppercase tracking-wide text-fg-meta">
                <th className="px-4 py-3 font-medium">#</th>
                <th className="px-4 py-3 font-medium">Validator</th>
                <th className="px-4 py-3 font-medium">Accuracy</th>
                <th className="px-4 py-3 font-medium">Cases Judged</th>
              </tr>
            </thead>
            <tbody>
              {rankedLeaderboard.map((v, i) => (
                <tr
                  key={v.name}
                  className={i === rankedLeaderboard.length - 1 ? "" : "border-b border-border-1"}
                >
                  <td className="px-4 py-3 text-fg-meta">{i + 1}</td>
                  <td className="px-4 py-3 font-brand-mono font-semibold">{v.name}</td>
                  <td className="px-4 py-3 font-semibold text-positive">
                    {v.accuracyPct}%
                  </td>
                  <td className="px-4 py-3 text-fg-meta">{v.casesJudged}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-6 text-[11px] text-fg-faint-2">
        Generated {new Date(analytics.generatedAt).toLocaleString()}
      </div>
    </div>
  );
}
