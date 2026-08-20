import Link from "next/link";

export function NetworkCta() {
  return (
    <section id="network" className="mx-auto max-w-[1160px] px-8 pb-24">
      <div className="flex flex-wrap items-center justify-between gap-10 rounded-[20px] border border-border-2 bg-surface-2 p-9 sm:p-14">
        <div className="max-w-[520px]">
          <h2 className="font-display text-2xl font-bold tracking-tight sm:text-[28px]">
            Start building on the Internet Court.
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-fg-dim-2">
            Nuance runs live on GenLayer&rsquo;s Testnet Bradbury. Fund an
            escrow, open a market, or file a dispute in minutes.
          </p>
        </div>
        <Link
          href="/app"
          className="shrink-0 rounded-[9px] bg-accent px-7 py-3.5 text-[15px] font-semibold text-accent-fg transition-opacity hover:opacity-85"
        >
          Launch App
        </Link>
      </div>
    </section>
  );
}
