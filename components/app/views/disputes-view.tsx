import type { Dispute } from "@/components/app/types";
import { StatusBadge } from "@/components/app/status-badge";
import { formatAddress } from "@/components/app/status";

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

      {disputes.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-[16px] border border-dashed border-border-4 bg-surface-1/50 px-6 py-16 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-border-4 bg-surface-2 text-xl text-fg-meta">
            ⚖
          </div>
          <div className="text-base font-semibold text-fg">No data available</div>
          <p className="mt-1 max-w-md text-sm text-fg-meta">
            There are currently no active disputes in the Internet Court.
          </p>
        </div>
      ) : (
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
                    {formatAddress(d.openedByAddress)}{" "}
                    <span className="text-fg-meta">vs</span>{" "}
                    {formatAddress(d.counterpartyAddress)}
                  </div>
                  <div className="mt-1.5 max-w-[520px] text-[13px] text-fg-meta">
                    {d.issue}
                  </div>
                </div>
                <StatusBadge status={d.statusKey} />
              </div>
              <div className="mt-2.5 font-brand-mono text-[13px] text-fg-bright">
                {d.amount.toLocaleString()} GEN at stake
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
