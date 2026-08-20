import type { MouseEvent } from "react";
import { WALLET_CATALOG } from "@/components/app/wallet-catalog";
import { useWalletDetection } from "@/components/app/use-wallet-detection";
import type { Eip1193Provider } from "@/components/app/eip1193";

export function WalletModal({
  onClose,
  onSelect,
  connecting,
  error,
}: {
  onClose: () => void;
  onSelect: (provider: Eip1193Provider, name: string) => void;
  connecting: boolean;
  error: string | null;
}) {
  const detected = useWalletDetection();
  const readyCount = WALLET_CATALOG.filter((w) => detected.has(w.rdns)).length;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay/60 p-4"
    >
      <div
        onClick={(e: MouseEvent) => e.stopPropagation()}
        className="w-full max-w-[560px] rounded-2xl border border-border-2 bg-surface-2 p-5"
        style={{ animation: "fadeUp 0.2s ease" }}
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="font-display text-base font-bold">
            Connect a wallet
          </div>
          <div
            onClick={onClose}
            className="cursor-pointer text-lg leading-none text-fg-meta transition-colors hover:text-fg"
          >
            ×
          </div>
        </div>

        <div className="mb-3 flex items-center justify-between text-[11px] uppercase tracking-wide text-fg-meta">
          <span>Wallets</span>
          {connecting ? (
            <span
              className="normal-case tracking-normal text-fg-hover"
              style={{ animation: "pulse-dot 1.2s ease infinite" }}
            >
              Confirm in your wallet…
            </span>
          ) : (
            <span className="flex items-center gap-1.5 normal-case tracking-normal text-positive-text">
              <span className="h-1.5 w-1.5 rounded-full bg-positive" />
              {readyCount} ready
            </span>
          )}
        </div>

        {error && (
          <div className="mb-3 rounded-lg border border-negative/35 bg-negative/12 px-3 py-2 text-xs text-negative-text">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {WALLET_CATALOG.map((w) => {
            const ready = detected.has(w.rdns);
            return (
              <div
                key={w.rdns}
                onClick={() => {
                  if (connecting) return;
                  const provider = detected.get(w.rdns);
                  if (ready && provider) {
                    onSelect(provider, w.name);
                  } else if (!ready) {
                    window.open(w.installUrl, "_blank", "noopener,noreferrer");
                  }
                }}
                className={`flex items-start gap-3 rounded-xl border border-border-2 bg-chip p-3.5 transition-colors hover:bg-chip-hover ${
                  connecting ? "cursor-default opacity-60" : "cursor-pointer"
                }`}
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg">
                  <w.Icon />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">{w.name}</div>
                  <div className="mt-0.5 text-xs leading-snug text-fg-meta">
                    {ready ? "Detected in this browser" : "Install the browser extension"}
                  </div>
                </div>
                <div
                  className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                    ready
                      ? "bg-positive/16 text-positive-text"
                      : "bg-neutral text-pending-text"
                  }`}
                >
                  {ready ? "Ready" : "Install"}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-3.5 flex items-start gap-2 rounded-lg border border-positive/25 bg-positive/10 p-3">
          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-positive" />
          <div className="text-xs leading-relaxed text-fg-dim-2">
            <span className="font-semibold text-positive-text">
              Sign-in only.
            </span>{" "}
            Connecting asks for a signature. It never moves funds or costs
            gas.
          </div>
        </div>
      </div>
    </div>
  );
}
