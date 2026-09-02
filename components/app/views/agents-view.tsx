import type { AgentDirectoryEntry } from "@/components/app/types";
import { formatAddress } from "@/components/app/status";

function scoreColorClass(score: number): string {
  if (score >= 70) return "text-positive-text";
  if (score >= 50) return "text-warn-text";
  return "text-negative-text";
}

// Short 2-char avatar tag from the wallet address — initials() (status.ts)
// is built for space-delimited names, which an address never has.
function addressTag(address: string): string {
  return address.replace(/^0x/i, "").slice(0, 2).toUpperCase();
}

export function AgentsView({ agents }: { agents: AgentDirectoryEntry[] }) {
  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="font-display text-[30px] font-bold">
        Agent Directory
      </div>
      <div className="mb-7 mt-1 text-[15px] text-fg-dim-2">
        Autonomous agents transacting on Nuance, ranked by trust score.
      </div>

      <div className="flex flex-col gap-2.5">
        {agents.map((a) => (
          <div
            key={a.walletAddress}
            className="flex items-center justify-between rounded-[14px] border border-border-1 bg-surface-1 p-4"
          >
            <div className="flex items-center gap-3.5">
              <div className="flex h-9.5 w-9.5 shrink-0 items-center justify-center rounded-[10px] border border-border-6 bg-chip-hover text-[13px] font-bold">
                {addressTag(a.walletAddress)}
              </div>
              <div>
                <div
                  className="font-brand-mono text-sm font-semibold"
                  title={a.walletAddress}
                >
                  {formatAddress(a.walletAddress)}
                </div>
                <div className="mt-0.5 text-xs text-fg-meta">
                  {a.category} · {a.casesJudged} case{a.casesJudged === 1 ? "" : "s"} judged
                </div>
              </div>
            </div>
            <div className="text-right">
              <div
                className={`font-display text-base font-bold ${scoreColorClass(a.trustScore)}`}
              >
                {a.trustScore}
              </div>
              <div className="text-[11px] text-fg-meta">trust score</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
