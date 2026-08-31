export function CreateEscrowView({
  formTitle,
  formCounterparty,
  formAmount,
  formCriteria,
  onTitleChange,
  onCounterpartyChange,
  onAmountChange,
  onCriteriaChange,
  onCancel,
  onSubmit,
}: {
  formTitle: string;
  formCounterparty: string;
  formAmount: string;
  formCriteria: string;
  onTitleChange: (v: string) => void;
  onCounterpartyChange: (v: string) => void;
  onAmountChange: (v: string) => void;
  onCriteriaChange: (v: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const disabled = !(formTitle.trim() && formCounterparty.trim() && formAmount);

  return (
    <div className="max-w-[560px]" style={{ animation: "fadeUp 0.3s ease" }}>
      <div
        onClick={onCancel}
        className="mb-4.5 inline-block cursor-pointer text-sm text-fg-meta transition-colors hover:text-fg"
      >
        ← Cancel
      </div>
      <div className="mb-6 font-display text-2xl font-bold">New Escrow</div>

      <div className="flex flex-col gap-4">
        <div>
          <div className="mb-1.5 text-[13px] text-fg-meta">
            Milestone title
          </div>
          <input
            value={formTitle}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="e.g. Landing page redesign"
            className="w-full rounded-lg border border-border-4 bg-surface-1 px-3 py-2.5 text-sm text-fg placeholder:text-fg-faint-2"
          />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] text-fg-meta">
            Counterparty wallet address
          </div>
          <input
            value={formCounterparty}
            onChange={(e) => onCounterpartyChange(e.target.value)}
            placeholder="0x…"
            className="w-full rounded-lg border border-border-4 bg-surface-1 px-3 py-2.5 font-brand-mono text-sm text-fg placeholder:text-fg-faint-2"
          />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] text-fg-meta">
            Amount (USDC)
          </div>
          <input
            value={formAmount}
            onChange={(e) => onAmountChange(e.target.value)}
            placeholder="1500"
            className="w-full rounded-lg border border-border-4 bg-surface-1 px-3 py-2.5 font-brand-mono text-sm text-fg placeholder:text-fg-faint-2"
          />
        </div>
        <div>
          <div className="mb-1.5 text-[13px] text-fg-meta">
            Adjudication criteria — what should validators check?
          </div>
          <textarea
            value={formCriteria}
            onChange={(e) => onCriteriaChange(e.target.value)}
            placeholder="e.g. Site matches Figma spec, loads under 2s, responsive on mobile"
            className="min-h-[80px] w-full resize-y rounded-lg border border-border-4 bg-surface-1 px-3 py-2.5 font-sans text-sm text-fg placeholder:text-fg-faint-2"
          />
        </div>
        <button
          onClick={onSubmit}
          disabled={disabled}
          className="mt-1.5 cursor-pointer rounded-[9px] border border-border-6 bg-chip-hover px-5 py-3.5 text-sm font-semibold transition-colors hover:bg-chip-hover-2 disabled:cursor-default"
          style={{ opacity: disabled ? 0.5 : 1 }}
        >
          Fund Escrow
        </button>
      </div>
    </div>
  );
}
