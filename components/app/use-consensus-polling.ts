"use client";

import { useEffect, useState } from "react";
import { getConsensusStatus, type ApiConsensusVerdict, type ApiValidatorResult } from "@/lib/api";

const POLL_INTERVAL_MS = 500;
// Mirrors backend ConsensusStage.DONE (app/enums.py) — the frontend has no
// shared enum with the Python backend, so this is pinned by comment instead.
const DONE_STAGE = 3;

export interface ConsensusPollState {
  stage: number;
  validator_results: ApiValidatorResult[] | null;
  verdict: ApiConsensusVerdict | null;
}

const IDLE_STATE: ConsensusPollState = {
  stage: 0,
  validator_results: null,
  verdict: null,
};

/**
 * Polls GET /consensus/{job_id} every 500ms while `jobId` is set, and
 * stops — clearing the timer — the moment the job reaches stage 3 (DONE),
 * `jobId` goes back to null, or the component unmounts.
 */
export function useConsensusPolling(jobId: string | null): ConsensusPollState {
  const [state, setState] = useState<ConsensusPollState>(IDLE_STATE);

  // Reset to idle synchronously when jobId changes, rather than via
  // setState inside the effect below — this is React's documented
  // "adjust state during render" pattern for resetting state when a prop
  // changes; setState-in-effect would cause an extra cascading render.
  const [trackedJobId, setTrackedJobId] = useState(jobId);
  if (jobId !== trackedJobId) {
    setTrackedJobId(jobId);
    setState(IDLE_STATE);
  }

  useEffect(() => {
    if (jobId == null) return;

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const status = await getConsensusStatus(Number(jobId));
        if (cancelled) return;
        setState({
          stage: status.stage,
          validator_results: status.validator_results,
          verdict: status.verdict,
        });
        if (status.stage >= DONE_STAGE) return; // done — stop scheduling further polls
      } catch (err) {
        if (cancelled) return;
        // A transient network blip or a 404 before the job row is
        // committed shouldn't kill polling — just retry next tick.
        console.error("Consensus poll failed:", err);
      }
      if (!cancelled) {
        timeoutId = setTimeout(tick, POLL_INTERVAL_MS);
      }
    }

    void tick();

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [jobId]);

  return state;
}
