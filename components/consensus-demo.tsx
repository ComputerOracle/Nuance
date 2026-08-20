"use client";

import { useEffect, useRef, useState } from "react";

type Stage = 0 | 1 | 2 | 3;
type Tone = "queued" | "active" | "done";

const VALIDATORS = ["Validator-Alpha", "Validator-Beta", "Validator-Gamma"];

const DOT_TONE_CLASSES: Record<Tone, string> = {
  queued: "bg-dot-queued",
  active: "bg-dot-active",
  done: "bg-dot-done",
};

function rowsForStage(stage: Stage) {
  return VALIDATORS.map((name, i) => {
    const myStage = i + 1;
    let icon = "···";
    let status = "Queued";
    let tone: Tone = "queued";

    if (stage === myStage || (stage >= 1 && stage < 3)) {
      icon = "◐";
      status = "Analyzing…";
      tone = "active";
    }
    if (stage >= 3) {
      icon = "✓";
      status = "Consensus recorded";
      tone = "done";
    }

    return { name, icon, status, tone };
  });
}

export function ConsensusDemo() {
  const [stage, setStage] = useState<Stage>(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
    };
  }, []);

  function runDemo() {
    setStage(1);
    timers.current.push(setTimeout(() => setStage(2), 800));
    timers.current.push(setTimeout(() => setStage(3), 1700));
  }

  const rows = rowsForStage(stage);
  const hasVerdict = stage === 3;
  const idle = stage === 0;

  return (
    <div
      className="rounded-2xl border border-border-2 bg-surface-2 p-5.5 opacity-0"
      style={{ animation: "fadeUp 0.4s ease 0.1s forwards" }}
    >
      <div className="mb-1 flex items-center justify-between">
        <div className="font-display text-sm font-bold">
          AI Validator Consensus
        </div>
        <div className="text-[11px] text-fg-faint-2">Live demo</div>
      </div>
      <div className="mb-4 text-xs text-fg-faint">
        Milestone: &ldquo;Checkout flow matches Figma spec&rdquo;
      </div>

      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div
            key={row.name}
            className="flex items-center gap-3 rounded-lg bg-surface-3 px-3 py-2.5"
          >
            <div
              className={`flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-full text-xs ${DOT_TONE_CLASSES[row.tone]}`}
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
              <div className="text-[11px] text-fg-faint">{row.status}</div>
            </div>
          </div>
        ))}
      </div>

      {hasVerdict && (
        <div
          className="mt-3.5 rounded-[10px] border border-verdict-border bg-verdict-bg p-3.5"
          style={{ animation: "fadeUp 0.3s ease" }}
        >
          <div className="mb-1.5 text-[13px] font-bold text-fg">
            Consensus: Approved · 96% confidence
          </div>
          <div className="text-xs leading-relaxed text-fg-dim">
            All three validators confirmed the deliverable meets spec. Escrow
            cleared for release.
          </div>
        </div>
      )}

      {idle && (
        <button
          onClick={runDemo}
          className="mt-3.5 w-full cursor-pointer rounded-lg border border-border-6 bg-chip-hover py-2.5 text-[13px] font-semibold transition-colors hover:bg-chip-hover-2"
        >
          Run consensus
        </button>
      )}
    </div>
  );
}
