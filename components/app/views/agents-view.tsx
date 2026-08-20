import type { AgentDirectoryEntry } from "@/components/app/types";
import { initials } from "@/components/app/status";

function scoreColorClass(score: number): string {
  if (score >= 70) return "text-positive-text";
  if (score >= 50) return "text-warn-text";
  return "text-negative-text";
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
            key={a.name}
            className="flex items-center justify-between rounded-[14px] border border-border-1 bg-surface-1 p-4"
          >
            <div className="flex items-center gap-3.5">
              <div className="flex h-9.5 w-9.5 shrink-0 items-center justify-center rounded-[10px] border border-border-6 bg-chip-hover text-[13px] font-bold">
                {initials(a.name)}
              </div>
              <div>
                <div className="text-sm font-semibold">{a.name}</div>
                <div className="mt-0.5 text-xs text-fg-meta">
                  {a.category} · {a.txns} txns
                </div>
              </div>
            </div>
            <div className="text-right">
              <div
                className={`font-display text-base font-bold ${scoreColorClass(a.score)}`}
              >
                {a.score}
              </div>
              <div className="text-[11px] text-fg-meta">trust score</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
