import type { ReactNode } from "react";
import { VALIDATOR_NAMES } from "@/components/app/data";

type Tone = "queued" | "active" | "done";

const DOT_TONE_CLASSES: Record<Tone, string> = {
  queued: "bg-dot-queued",
  active: "bg-review/30",
  done: "bg-positive/30",
};

export function consensusRows(
  stage: number,
  analyzingLabel: string,
  doneLabel: string
) {
  return VALIDATOR_NAMES.map((name, i) => {
    const myStage = i + 1;
    let icon = "···";
    let statusText = "Queued";
    let tone: Tone = "queued";

    if (stage === myStage || (stage >= 1 && stage < 3)) {
      icon = "◐";
      statusText = analyzingLabel;
      tone = "active";
    }
    if (stage >= 3) {
      icon = "✓";
      statusText = doneLabel;
      tone = "done";
    }

    return { name, icon, statusText, tone };
  });
}

export interface ConsensusVerdict {
  label: string;
  colorClass: string;
  panelBgClass: string;
  panelBorderClass: string;
  confidence?: number;
  reasoning: string;
  actions?: ReactNode;
}

export function ConsensusPanel({
  title,
  subtitle,
  stage,
  analyzingLabel,
  doneLabel,
  idleText,
  verdict,
  sticky = false,
}: {
  title: string;
  subtitle: string;
  stage: number;
  analyzingLabel: string;
  doneLabel: string;
  idleText: string;
  verdict: ConsensusVerdict | null;
  sticky?: boolean;
}) {
  const rows = stage > 0 ? consensusRows(stage, analyzingLabel, doneLabel) : [];

  return (
    <div
      className={`h-fit rounded-2xl border border-border-2 bg-surface-2 p-5 ${sticky ? "lg:sticky lg:top-10" : ""}`}
    >
      <div className="mb-1 font-display text-[15px] font-bold">{title}</div>
      <div className="mb-4 text-[13px] text-fg-meta">{subtitle}</div>

      {rows.length > 0 && (
        <div className="flex flex-col gap-2.5">
          {rows.map((row) => (
            <div
              key={row.name}
              className="flex items-center gap-3 rounded-[9px] bg-surface-3 px-3 py-2.5"
            >
              <div
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs ${DOT_TONE_CLASSES[row.tone]}`}
                style={
                  row.tone === "active"
                    ? { animation: "spin 1.1s linear infinite" }
                    : undefined
                }
              >
                {row.icon}
              </div>
              <div className="flex-1">
                <div className="text-[13px] font-semibold">{row.name}</div>
                <div className="text-xs text-fg-meta">{row.statusText}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {verdict && (
        <div
          className={`mt-4 rounded-[10px] border p-4 ${verdict.panelBgClass} ${verdict.panelBorderClass}`}
          style={{ animation: "fadeUp 0.3s ease" }}
        >
          <div className="mb-2 flex items-center gap-2">
            <div className={`text-sm font-bold ${verdict.colorClass}`}>
              {verdict.label}
            </div>
            {verdict.confidence !== undefined && (
              <div className="text-xs text-fg-meta">
                · {verdict.confidence}% confidence
              </div>
            )}
          </div>
          <div className="text-[13px] leading-relaxed text-fg-bright">
            {verdict.reasoning}
          </div>
          {verdict.actions && (
            <div className="mt-3.5 flex gap-2.5">{verdict.actions}</div>
          )}
        </div>
      )}

      {rows.length === 0 && !verdict && (
        <div className="py-6 text-center text-[13px] text-fg-faint-2">
          {idleText}
        </div>
      )}
    </div>
  );
}
