const USE_CASES = [
  {
    title: "Escrow & bounties",
    body: "Freelance and bounty payouts released only when validators confirm the work meets the brief — no manual sign-off.",
  },
  {
    title: "Prediction markets",
    body: "Bet on fuzzy, real-world outcomes — legal disputes, PR fallout, campaign compliance — settled by AI reading the news, not an API.",
  },
  {
    title: "Dispute court",
    body: "Autonomous agents transacting at machine speed get a plain-language arbitration venue when they disagree.",
  },
  {
    title: "Governance",
    body: "DAOs write bylaws in plain English; AI consensus acts as the judicial branch checking spend and actions against intent.",
  },
];

export function UseCases() {
  return (
    <section id="use-cases" className="mx-auto max-w-[1160px] px-8 pb-24">
      <div className="mb-3 text-[13px] uppercase tracking-[0.6px] text-fg-faint">
        What you can build
      </div>
      <h2 className="max-w-[640px] font-display text-[28px] font-bold tracking-tight sm:text-[34px]">
        Four tracks, one adjudication layer.
      </h2>

      <div className="mt-11 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {USE_CASES.map((useCase) => (
          <div
            key={useCase.title}
            className="rounded-[14px] border border-border-1 bg-surface-1 p-7"
          >
            <div className="text-lg font-bold">{useCase.title}</div>
            <div className="mt-2.5 text-sm leading-relaxed text-fg-dim-2">
              {useCase.body}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
