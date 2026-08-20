const STEPS = [
  {
    number: "01",
    title: "Submit the claim",
    body: "A deliverable, a real-world event, or a dispute is filed in plain language — a PR link, a news outcome, an agent transaction log.",
  },
  {
    number: "02",
    title: "Validators read it",
    body: "Independent GenVM validators crawl the web, read the artifact, and reason over the stated criteria — no oracle feed required.",
  },
  {
    number: "03",
    title: "Consensus settles it",
    body: "When validators agree, funds release, markets resolve, or a ruling is enforced on-chain automatically.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="mx-auto max-w-[1160px] px-8 py-24">
      <div className="mb-3 text-[13px] uppercase tracking-[0.6px] text-fg-faint">
        How it works
      </div>
      <h2 className="max-w-[640px] font-display text-[28px] font-bold tracking-tight sm:text-[34px]">
        Every ruling follows the same three steps.
      </h2>

      <div className="mt-11 grid grid-cols-1 gap-5 sm:grid-cols-3">
        {STEPS.map((step) => (
          <div
            key={step.number}
            className="rounded-[14px] border border-border-1 bg-surface-1 p-6.5"
          >
            <div className="font-brand-mono text-[13px] text-fg-faint-2">
              {step.number}
            </div>
            <div className="mt-3.5 text-[17px] font-bold">{step.title}</div>
            <div className="mt-2.5 text-sm leading-relaxed text-fg-dim-2">
              {step.body}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
