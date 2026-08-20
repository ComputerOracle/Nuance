/**
 * Brand mark. The source design's PNG assets (assets/nuance-icon.png,
 * assets/nuance-logo.png) came back truncated when fetched from the design
 * project (256KB read cap on a much larger file), so this is a hand-built
 * SVG stand-in that reads the same: three overlapping validator "nodes"
 * converging on a single ruling, in a rounded dark tile.
 */
export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-lg bg-black"
      style={{ width: size, height: size }}
    >
      <svg
        viewBox="0 0 24 24"
        width={size * 0.62}
        height={size * 0.62}
        fill="none"
      >
        <circle cx="7" cy="7.5" r="3" fill="oklch(0.94 0.01 279)" />
        <circle cx="17" cy="7.5" r="3" fill="oklch(0.65 0.01 279)" />
        <circle cx="12" cy="16" r="3" fill="oklch(0.94 0.01 279)" />
        <path
          d="M9.4 9.2 10.6 13.6 M14.6 9.2 13.4 13.6"
          stroke="oklch(0.4 0.01 279)"
          strokeWidth="1.1"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="font-display text-lg font-bold text-fg">Nuance</span>
    </div>
  );
}
