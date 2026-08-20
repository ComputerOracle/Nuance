import type { Dispute } from "@/components/app/types";
import { StatusBadge } from "@/components/app/status-badge";

export function DisputesView({
  disputes,
  onOpen,
}: {
  disputes: Dispute[];
  onOpen: (id: number) => void;
}) {
  return (
    <div style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="font-display text-[30px] font-bold">Dispute Court</div>
      <div className="mb-7 mt-1 text-[15px] text-fg-dim-2">
        Inter-agent conflicts settled by GenLayer&rsquo;s Internet Court.
      </div>

      <div className="flex flex-col gap-2.5">
        {disputes.map((d) => (
          <div
            key={d.id}
            onClick={() => onOpen(d.id)}
            className="cursor-pointer rounded-[14px] border border-border-1 bg-surface-1 p-5 transition-colors hover:border-border-6"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[15px] font-semibold">
                  {d.agentA} <span className="text-fg-meta">vs</span>{" "}
                  {d.agentB}
                </div>
                <div className="mt-1.5 max-w-[520px] text-[13px] text-fg-meta">
                  {d.issue}
                </div>
              </div>
              <StatusBadge status={d.statusKey} />
            </div>
            <div className="mt-2.5 font-brand-mono text-[13px] text-fg-bright">
              {d.amount.toLocaleString()} USDC at stake
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
