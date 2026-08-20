const ITEMS = [
  "EVM-compatible L2",
  "GenVM · Python Intelligent Contracts",
  "LayerZero cross-chain messaging",
  "The Internet Court for the machine economy",
];

export function TickerStrip() {
  return (
    <div className="border-y border-border-3 py-4.5">
      <div className="mx-auto flex max-w-[1160px] flex-wrap gap-10 px-8 text-[13px] text-fg-faint-2">
        {ITEMS.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </div>
  );
}
