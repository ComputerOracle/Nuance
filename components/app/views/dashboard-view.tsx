import type { Escrow } from "@/components/app/types";
import { StatusBadge } from "@/components/app/status-badge";
import { activeMilestoneIndex, initials } from "@/components/app/status";

export function DashboardView({
  escrows,
  onOpenCreate,
  onOpenEscrow,
}: {
  escrows: Escrow[];
  onOpenCreate: () => void;
  onOpenEscrow: (id: number) => void;
}) {
  const totalEscrowed = escrows.reduce((s, e) => s + e.total, 0);
  const activeReviewCount = escrows.filter(
    (e) => e.statusKey === "in_review"
  ).length;

  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <div className="font-display text-[30px] font-bold">Escrows</div>
          <div className="mt-1 text-[15px] text-fg-dim-2">
            Milestones adjudicated by AI-validator consensus.
          </div>
        </div>
        <button
          onClick={onOpenCreate}
          className="cursor-pointer rounded-[9px] border border-border-6 bg-chip-hover px-5 py-3 text-sm font-semibold transition-colors hover:bg-chip-hover-2"
        >
          + New Escrow
        </button>
      </div>

      <div className="mb-9 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-[14px] border border-border-1 bg-surface-1 p-5">
          <div className="text-xs uppercase tracking-wide text-fg-meta">
            Total Escrowed
          </div>
          <div className="mt-1.5 font-display text-[26px] font-bold">
            {totalEscrowed.toLocaleString()}
          </div>
        </div>
        <div className="rounded-[14px] border border-border-1 bg-surface-1 p-5">
          <div className="text-xs uppercase tracking-wide text-fg-meta">
            Active Reviews
          </div>
          <div className="mt-1.5 font-display text-[26px] font-bold">
            {activeReviewCount}
          </div>
        </div>
        <div className="rounded-[14px] border border-border-1 bg-surface-1 p-5">
          <div className="text-xs uppercase tracking-wide text-fg-meta">
            Consensus Accuracy
          </div>
          <div className="mt-1.5 font-display text-[26px] font-bold text-positive">
            98.4%
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        {escrows.map((e) => {
          const activeIdx = activeMilestoneIndex(e.milestones);
          return (
            <div
              key={e.id}
              onClick={() => onOpenEscrow(e.id)}
              className="flex cursor-pointer items-center justify-between rounded-[14px] border border-border-1 bg-surface-1 p-5 transition-colors hover:border-border-6"
            >
              <div className="flex items-center gap-4">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[10px] border border-border-6 bg-chip-hover font-display font-bold">
                  {initials(e.title)}
                </div>
                <div>
                  <div className="text-[15px] font-semibold">{e.title}</div>
                  <div className="mt-0.5 text-[13px] text-fg-meta">
                    with {e.counterparty} · {e.milestones[activeIdx].name}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-5">
                <div className="text-right">
                  <div className="font-brand-mono text-sm font-semibold">
                    {e.total.toLocaleString()}
                  </div>
                  <div className="text-xs text-fg-meta">USDC</div>
                </div>
                <StatusBadge status={e.statusKey} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
