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

export function SettingsView({
  notifyOn,
  autoEscalateOn,
  onToggleNotify,
  onToggleAutoEscalate,
}: {
  notifyOn: boolean;
  autoEscalateOn: boolean;
  onToggleNotify: () => void;
  onToggleAutoEscalate: () => void;
}) {
  return (
    <div className="max-w-[520px]" style={{ animation: "fadeUp 0.3s ease" }}>
      <div className="mb-7 font-display text-[30px] font-bold">Settings</div>

      <div className="flex flex-col gap-3.5">
        <div className="flex items-center justify-between rounded-xl border border-border-1 bg-surface-1 p-4.5">
          <div>
            <div className="text-sm font-semibold">Network</div>
            <div className="mt-0.5 text-xs text-fg-meta">
              Testnet Bradbury
            </div>
          </div>
          <div className="rounded-full bg-positive/15 px-3 py-1.5 text-xs font-semibold text-positive-text">
            Connected
          </div>
        </div>

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
