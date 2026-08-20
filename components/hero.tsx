import Link from "next/link";
import { ConsensusDemo } from "@/components/consensus-demo";

const STATS = [
  { value: "98.4%", label: "Consensus accuracy" },
  { value: "3-of-3", label: "Validator quorum" },
  { value: "<2min", label: "Avg. ruling time" },
];

export function Hero() {
  return (
    <div className="mx-auto grid max-w-[1160px] grid-cols-1 items-center gap-14 px-8 py-16 lg:grid-cols-[1fr_0.85fr] lg:py-22">
      <div className="opacity-0" style={{ animation: "fadeUp 0.4s ease forwards" }}>
        <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border-4 bg-chip px-3 py-1.5 text-xs text-fg-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-fg" />
          Built on GenLayer · Testnet Bradbury
        </div>

        <h1 className="font-display text-[38px] font-bold leading-[1.08] tracking-tight sm:text-[52px]">
          Contracts that understand nuance, not just logic.
        </h1>

        <p className="mt-5 max-w-[520px] text-[17px] leading-relaxed text-fg-dim">
          Nuance settles agreements traditional smart contracts can&rsquo;t:
          was the work actually good, did the campaign really mislead, who
          broke the deal. AI-validator consensus reads the evidence and
          rules — no human bottleneck.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/app"
            className="rounded-[9px] bg-accent px-6 py-3.5 text-[15px] font-semibold text-accent-fg transition-opacity hover:opacity-85"
          >
            Launch App
          </Link>
          <a
            href="#how"
            className="rounded-[9px] border border-border-5 px-6 py-3.5 text-[15px] font-semibold transition-colors hover:bg-chip"
          >
            See how it works
          </a>
        </div>

        <div className="mt-12 flex flex-wrap gap-9">
          {STATS.map((stat) => (
            <div key={stat.label}>
              <div className="font-display text-2xl font-bold">
                {stat.value}
              </div>
              <div className="mt-0.5 text-xs text-fg-faint-2">
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      <ConsensusDemo />
    </div>
  );
}
