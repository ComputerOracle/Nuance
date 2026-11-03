import { useState } from "react";
import * as api from "@/lib/api";

function Toggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <div
      onClick={onToggle}
      className={`relative h-[26px] w-[44px] shrink-0 cursor-pointer rounded-full transition-colors ${
        on ? "bg-review" : "bg-neutral"
      }`}
    >
      <div
        className="absolute top-[3px] h-5 w-5 rounded-full bg-white transition-[left]"
        style={{ left: on ? "22px" : "3px", transitionDuration: "0.15s" }}
      />
    </div>
  );
}

export const MASTER_TREASURY_ADDRESS = "0x41648dE45Cc4D0172beCd4Db0A0A0b459C383705";

export function SettingsView({
  notifyOn,
  autoEscalateOn,
  onToggleNotify,
  onToggleAutoEscalate,
  connectedWalletAddress,
}: {
  notifyOn: boolean;
  autoEscalateOn: boolean;
  onToggleNotify: () => void;
  onToggleAutoEscalate: () => void;
  connectedWalletAddress?: string | null;
}) {
  const [isSweeping, setIsSweeping] = useState(false);
  const [sweepResult, setSweepResult] = useState<string | null>(null);

  const isTreasuryOwner =
    Boolean(connectedWalletAddress) &&
    connectedWalletAddress?.toLowerCase() === MASTER_TREASURY_ADDRESS.toLowerCase();

  async function handleSweepContract(contractType: string) {
    setIsSweeping(true);
    setSweepResult(null);
    try {
      const contractAddress =
        contractType === "governance"
          ? process.env.NEXT_PUBLIC_GOVERNANCE_CONTRACT_ADDRESS
          : contractType === "escrow"
            ? process.env.NEXT_PUBLIC_ESCROW_CONTRACT_ADDRESS
            : process.env.NEXT_PUBLIC_PREDICTION_MARKET_CONTRACT_ADDRESS;

      if (!contractAddress) {
        setSweepResult("Contract address not configured in environment.");
        return;
      }

      const res = await api.requestRescueRelayer(
        contractAddress,
        MASTER_TREASURY_ADDRESS,
        `admin_${contractType}_sweep`,
        ""
      );
      setSweepResult(res.message || "Sweep to Master Treasury initiated.");
    } catch (err) {
      setSweepResult(err instanceof Error ? err.message : "Failed to initiate sweep.");
    } finally {
      setIsSweeping(false);
    }
  }

  return (
    <div className="max-w-[620px]" style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="mb-7 font-display text-[30px] font-bold">Settings & Treasury</div>

      <div className="flex flex-col gap-4">
        {/* Network & RPC Status */}
        <div className="flex items-center justify-between rounded-xl border border-border-1 bg-surface-1 p-4.5">
          <div>
            <div className="text-sm font-semibold">Network</div>
            <div className="mt-0.5 text-xs text-fg-meta">
              GenLayer Testnet Bradbury (Chain ID 4221)
            </div>
          </div>
          <div className="rounded-full bg-positive/15 px-3 py-1.5 text-xs font-semibold text-positive-text">
            Connected
          </div>
        </div>

        {/* Master Withdrawable Treasury */}
        <div className="rounded-xl border border-border-1 bg-surface-1 p-4.5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold">Master Protocol Treasury</div>
              <div className="mt-0.5 text-xs text-fg-meta">
                All protocol fees, swept funds, and rescue balances route to this withdrawable account
              </div>
            </div>
            <span className="rounded-full bg-review/15 px-2.5 py-1 text-[11px] font-semibold text-review-text">
              Withdrawable EOA
            </span>
          </div>

          <div className="mt-3.5 rounded-lg border border-border-4 bg-surface-3 p-3 font-brand-mono text-xs text-fg-bright break-all">
            {MASTER_TREASURY_ADDRESS}
          </div>

          <div className="mt-2.5 flex items-center justify-between text-xs text-fg-meta">
            <span>Treasury Status: <strong className="text-positive-text">Active & Liquid</strong></span>
            {isTreasuryOwner ? (
              <span className="font-semibold text-positive-text">✓ You are connected as Treasury</span>
            ) : (
              <span className="text-fg-faint-2">Funds are fully withdrawable by holder</span>
            )}
          </div>

          <div className="mt-4 pt-3.5 border-t border-border-1">
            <div className="text-xs font-semibold text-fg-bright mb-2">Emergency Contract Sweeps</div>
            <div className="text-[11px] text-fg-meta mb-3">
              Sweep trapped or unreleased contract GEN directly into the Master Treasury:
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => handleSweepContract("escrow")}
                disabled={isSweeping}
                className="cursor-pointer rounded-lg border border-border-6 bg-surface-2 px-3 py-1.5 text-xs font-semibold text-fg transition-colors hover:bg-chip-hover disabled:opacity-50"
              >
                Sweep Escrows
              </button>
              <button
                onClick={() => handleSweepContract("governance")}
                disabled={isSweeping}
                className="cursor-pointer rounded-lg border border-border-6 bg-surface-2 px-3 py-1.5 text-xs font-semibold text-fg transition-colors hover:bg-chip-hover disabled:opacity-50"
              >
                Sweep Governance
              </button>
              <button
                onClick={() => handleSweepContract("prediction")}
                disabled={isSweeping}
                className="cursor-pointer rounded-lg border border-border-6 bg-surface-2 px-3 py-1.5 text-xs font-semibold text-fg transition-colors hover:bg-chip-hover disabled:opacity-50"
              >
                Sweep Prediction Market
              </button>
            </div>

            {sweepResult && (
              <div className="mt-2.5 rounded-lg border border-positive/30 bg-positive/10 p-2.5 text-xs text-positive-text">
                {sweepResult}
              </div>
            )}
          </div>
        </div>

        {/* Notifications & Automation */}
        <div className="flex items-center justify-between rounded-xl border border-border-1 bg-surface-1 p-4.5">
          <div>
            <div className="text-sm font-semibold">
              Consensus notifications
            </div>
            <div className="mt-0.5 text-xs text-fg-meta">
              Alert me when a validator ruling completes
            </div>
          </div>
          <Toggle on={notifyOn} onToggle={onToggleNotify} />
        </div>

        <div className="flex items-center justify-between rounded-xl border border-border-1 bg-surface-1 p-4.5">
          <div>
            <div className="text-sm font-semibold">
              Auto-escalate disputes
            </div>
            <div className="mt-0.5 text-xs text-fg-meta">
              Send unresolved reviews to the Internet Court after 48h
            </div>
          </div>
          <Toggle on={autoEscalateOn} onToggle={onToggleAutoEscalate} />
        </div>
      </div>
    </div>
  );
}

