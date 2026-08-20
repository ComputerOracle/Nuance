import { Logo } from "@/components/logo";
import type { View, WalletStatus } from "@/components/app/types";
import { GENLAYER_BRADBURY } from "@/components/app/genlayer-chain";

const NAV_DEFS: { key: string; label: string; views: View[] }[] = [
  { key: "dashboard", label: "Dashboard", views: ["dashboard", "detail", "create"] },
  {
    key: "predictions",
    label: "Prediction Markets",
    views: ["predictions", "predictionDetail"],
  },
  {
    key: "disputes",
    label: "Dispute Court",
    views: ["disputes", "disputeDetail"],
  },
  { key: "governance", label: "Governance", views: ["governance"] },
  { key: "validators", label: "Validators", views: ["validators"] },
  { key: "agents", label: "Agent Directory", views: ["agents"] },
  { key: "settings", label: "Settings", views: ["settings"] },
];

export function Sidebar({
  view,
  onNavigate,
  walletStatus,
  walletAddress,
  walletBalance,
  isWrongNetwork,
  walletError,
  onOpenWalletModal,
  onDisconnect,
  onSwitchNetwork,
}: {
  view: View;
  onNavigate: (key: string) => void;
  walletStatus: WalletStatus;
  walletAddress: string;
  walletBalance: string;
  isWrongNetwork: boolean;
  walletError: string | null;
  onOpenWalletModal: () => void;
  onDisconnect: () => void;
  onSwitchNetwork: () => void;
}) {
  return (
    <div className="sticky top-0 flex h-screen w-[248px] shrink-0 flex-col gap-6 overflow-y-auto border-r border-border-1 bg-surface-3 p-5 py-7">
      <Logo size={34} />

      <nav className="flex flex-col gap-0.5">
        {NAV_DEFS.map((n) => {
          const active = n.views.includes(view);
          return (
            <div
              key={n.key}
              onClick={() => onNavigate(n.key)}
              className={`flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm transition-colors hover:bg-nav-active hover:text-fg ${
                active
                  ? "bg-nav-active font-semibold text-fg"
                  : "font-medium text-fg-meta"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${active ? "bg-review" : "bg-dot-queued"}`}
              />
              {n.label}
            </div>
          );
        })}
      </nav>

      <div className="mt-auto flex flex-col gap-2">
        {walletError && walletStatus !== "connecting" && (
          <div className="rounded-lg border border-negative/35 bg-negative/12 px-3 py-2 text-[11px] leading-snug text-negative-text">
            {walletError}
          </div>
        )}

        <div className="rounded-xl border border-border-1 bg-surface-1 p-3.5">
          {walletStatus === "connected" ? (
            <>
              <div className="mb-1.5 flex items-center justify-between">
                <div className="text-[11px] uppercase tracking-wide text-fg-meta">
                  Wallet
                </div>
                <div
                  onClick={onDisconnect}
                  className="cursor-pointer text-[11px] text-fg-faint-2 transition-colors hover:text-fg"
                >
                  Disconnect
                </div>
              </div>
              <div className="font-brand-mono text-[13px] text-fg-bright">
                {walletAddress}
              </div>
              <div className="mt-1 text-xs text-fg-meta">
                {walletBalance || "…"}{" "}
                <span className="font-semibold text-fg">
                  {GENLAYER_BRADBURY.nativeCurrency.symbol}
                </span>
              </div>
              {isWrongNetwork ? (
                <div className="mt-2.5 flex items-center justify-between gap-2 rounded-lg border border-negative/35 bg-negative/12 px-2.5 py-2">
                  <span className="text-[11px] text-negative-text">
                    Wrong network
                  </span>
                  <button
                    onClick={onSwitchNetwork}
                    className="cursor-pointer text-[11px] font-semibold text-negative-text underline underline-offset-2"
                  >
                    Switch
                  </button>
                </div>
              ) : (
                <div className="mt-2 text-[11px] text-fg-faint-2">
                  Testnet Bradbury
                </div>
              )}
            </>
          ) : walletStatus === "connecting" ? (
            <div
              className="py-1.5 text-center text-sm text-fg-hover"
              style={{ animation: "pulse-dot 1.2s ease infinite" }}
            >
              Confirm in your wallet…
            </div>
          ) : (
            <>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-fg-meta">
                Wallet
              </div>
              <div className="mb-2.5 text-xs text-fg-meta">
                Connect a wallet to fund escrows and place bets.
              </div>
              <button
                onClick={onOpenWalletModal}
                className="w-full cursor-pointer rounded-lg border border-border-6 bg-chip-hover py-2.5 text-[13px] font-semibold transition-colors hover:bg-chip-hover-2"
              >
                Connect Wallet
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
