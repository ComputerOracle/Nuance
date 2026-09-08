"use client";

import { useEffect, useRef, useState } from "react";
import { getConsensusStatus, type ApiConsensusVerdict, type ApiValidatorResult } from "@/lib/api";

const POLL_INTERVAL_MS = 500;
// How long to wait for the socket to open before giving up on it and
// polling instead — a slow/blocked WS shouldn't stall the UI indefinitely.
const WS_CONNECT_TIMEOUT_MS = 1500;
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

function consensusWsUrl(jobId: string): string {
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010";
  // http(s) -> ws(s), same host/port as the REST API — matches how
  // API_BASE itself is derived in lib/api.ts.
  const wsBase = apiBase.replace(/^http/, "ws");
  return `${wsBase}/consensus/ws/${jobId}`;
}

/**
 * Tracks GET/WS /consensus/{job_id} while `jobId` is set, stopping — closing
 * the socket or clearing the poll timer — the moment the job reaches stage 3
 * (DONE), `jobId` goes back to null, or the component unmounts.
 *
 * Prefers a live WebSocket (backend/app/routers/consensus.py's
 * `consensus_status_ws`, a single connection the backend polls server-side
 * and forwards from) over the old ~500ms HTTP polling loop, but falls back
 * to that same polling automatically if the socket never opens in time, or
 * drops before the job is DONE — a flaky proxy, no WS support on the
 * deployment target, etc. shouldn't leave the panel stuck.
 */
export function useConsensusPolling(jobId: string | null): ConsensusPollState {
  const [state, setState] = useState<ConsensusPollState>(IDLE_STATE);

  // Reset to idle synchronously when jobId changes, rather than via
  // setState inside the effect below — this is React's documented
  // "adjust state during render" pattern for resetting state when a prop
  // changes; setState-in-effect would cause an extra cascading render.
  const [trackedJobId, setTrackedJobId] = useState(jobId);
  const stageRef = useRef(0);
  if (jobId !== trackedJobId) {
    setTrackedJobId(jobId);
    setState(IDLE_STATE);
    // stageRef itself resets in the effect below, not here — mutating a
    // ref during render (as opposed to state, via setState above, which
    // is React's own documented "adjust state during render" pattern) is
    // not render-safe: a render that gets thrown away/re-run (React
    // Strict Mode, concurrent rendering) would still have mutated it.
  }

  useEffect(() => {
    if (jobId == null) return;

    // The one place stageRef actually resets — synchronous with this
    // effect starting for the new jobId, before anything below can read
    // it, so there's no window where it holds a stale value from a
    // previous job.
    stageRef.current = 0;

    let cancelled = false;
    let pollTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let connectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;
    let polling = false;

    async function pollTick() {
      try {
        const status = await getConsensusStatus(Number(jobId));
        if (cancelled) return;
        stageRef.current = status.stage;
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
        pollTimeoutId = setTimeout(pollTick, POLL_INTERVAL_MS);
      }
    }

    function fallBackToPolling() {
      if (polling || cancelled || stageRef.current >= DONE_STAGE) return;
      polling = true;
      void pollTick();
    }

    try {
      socket = new WebSocket(consensusWsUrl(jobId));
    } catch (err) {
      console.error("Consensus WS setup failed, polling instead:", err);
      fallBackToPolling();
      socket = null;
    }

    if (socket) {
      connectTimeoutId = setTimeout(() => {
        if (!cancelled && socket && socket.readyState !== WebSocket.OPEN) {
          socket.close();
        }
      }, WS_CONNECT_TIMEOUT_MS);

      socket.onopen = () => {
        if (connectTimeoutId) clearTimeout(connectTimeoutId);
      };

      socket.onmessage = (event) => {
        if (cancelled) return;
        try {
          const payload = JSON.parse(event.data) as ConsensusPollState & { error?: string };
          if (payload.error) return; // job not found (yet) — wait for a real tick or the close below
          stageRef.current = payload.stage;
          setState({
            stage: payload.stage,
            validator_results: payload.validator_results,
            verdict: payload.verdict,
          });
        } catch (err) {
          console.error("Bad consensus WS payload:", err);
        }
      };

      socket.onerror = () => {
        // onclose always follows in browsers — let that drive the fallback
        // so there's one place deciding whether to start polling.
      };

      socket.onclose = () => {
        if (connectTimeoutId) clearTimeout(connectTimeoutId);
        fallBackToPolling();
      };
    }

    return () => {
      cancelled = true;
      if (connectTimeoutId) clearTimeout(connectTimeoutId);
      if (pollTimeoutId) clearTimeout(pollTimeoutId);
      socket?.close();
    };
  }, [jobId]);

  return state;
}
