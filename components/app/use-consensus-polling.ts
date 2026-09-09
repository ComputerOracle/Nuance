"use client";

import { useEffect, useRef, useState } from "react";
import { getConsensusStatus, type ApiConsensusVerdict, type ApiValidatorResult } from "@/lib/api";

const POLL_INTERVAL_MS = 500;
// How long to wait for the socket/EventSource to open before giving up on
// it and falling further down the chain — a slow/blocked transport
// shouldn't stall the UI indefinitely.
const WS_CONNECT_TIMEOUT_MS = 1500;
const SSE_CONNECT_TIMEOUT_MS = 1500;
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

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010";
}

function consensusWsUrl(jobId: string): string {
  // http(s) -> ws(s), same host/port as the REST API — matches how
  // API_BASE itself is derived in lib/api.ts.
  return `${apiBase().replace(/^http/, "ws")}/consensus/ws/${jobId}`;
}

function consensusSseUrl(jobId: string): string {
  return `${apiBase()}/consensus/sse/${jobId}`;
}

/**
 * Tracks GET/WS/SSE /consensus/{job_id} while `jobId` is set, stopping —
 * closing the socket/EventSource or clearing the poll timer — the moment
 * the job reaches stage 3 (DONE), `jobId` goes back to null, or the
 * component unmounts.
 *
 * Three tiers, in order (ROADMAP.md Part 3 5.2's SSE fallback item added
 * the middle one — WS and plain polling both predate it):
 *   1. WebSocket (backend/app/routers/consensus.py's `consensus_status_ws`)
 *      — the primary path, one connection the backend polls/subscribes
 *      server-side and forwards from.
 *   2. Server-Sent Events (`consensus_status_sse`) — for a network that
 *      blocks the WS upgrade handshake specifically but passes normal
 *      HTTP(S) through fine (some corporate proxies do exactly this). A
 *      live push channel over a plain GET beats falling all the way back
 *      to polling.
 *   3. The original ~500ms HTTP polling loop — always available, since
 *      it's just repeated plain GETs; the fallback beneath both of the
 *      above if neither transport ever connects or either drops before
 *      the job is DONE.
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
    // A const alias, not the raw parameter — TS discards narrowing across
    // closure boundaries for a mutable parameter, and fallBackToSse below
    // (a nested function) needs jobId to still read as `string`, not
    // `string | null`, when it calls consensusSseUrl.
    const activeJobId = jobId;

    // The one place stageRef actually resets — synchronous with this
    // effect starting for the new jobId, before anything below can read
    // it, so there's no window where it holds a stale value from a
    // previous job.
    stageRef.current = 0;

    let cancelled = false;
    let pollTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let wsConnectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let sseConnectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;
    let eventSource: EventSource | null = null;
    let polling = false;
    let sseStarted = false;

    function applyPayload(payload: ConsensusPollState & { error?: string }) {
      if (cancelled) return;
      if (payload.error) return; // job not found (yet) — wait for a real tick or the close below
      stageRef.current = payload.stage;
      setState({
        stage: payload.stage,
        validator_results: payload.validator_results,
        verdict: payload.verdict,
      });
    }

    async function pollTick() {
      try {
        const status = await getConsensusStatus(Number(activeJobId));
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

    function fallBackToSse() {
      if (sseStarted || cancelled || stageRef.current >= DONE_STAGE) return;
      sseStarted = true;

      try {
        eventSource = new EventSource(consensusSseUrl(activeJobId));
      } catch (err) {
        console.error("Consensus SSE setup failed, polling instead:", err);
        eventSource = null;
        fallBackToPolling();
        return;
      }

      sseConnectTimeoutId = setTimeout(() => {
        if (!cancelled && eventSource && eventSource.readyState !== EventSource.OPEN) {
          eventSource.close();
          fallBackToPolling();
        }
      }, SSE_CONNECT_TIMEOUT_MS);

      eventSource.onopen = () => {
        if (sseConnectTimeoutId) clearTimeout(sseConnectTimeoutId);
      };

      // Bare `data:` payloads (regular ticks + the not-found error case)
      // land here, same shape/handling as the WS `onmessage` above.
      eventSource.onmessage = (event) => {
        if (cancelled) return;
        try {
          applyPayload(JSON.parse(event.data));
        } catch (err) {
          console.error("Bad consensus SSE payload:", err);
        }
      };

      // The backend closes the stream itself with a named `done` event
      // once the job reaches DONE — see routers/consensus.py's own
      // docstring on why that's a named event specifically (a plain
      // EventSource has no other way to distinguish "ended on purpose"
      // from "connection dropped", and would otherwise auto-reconnect).
      eventSource.addEventListener("done", () => {
        eventSource?.close();
      });

      // A real EventSource fires its own native "error" for any
      // transport-level failure (not a server-sent payload — see
      // realtime.format_sse's docstring on why the backend never sends a
      // named `event: error` for exactly this reason). Reconnect attempts
      // land here too on every drop; once the job is actually DONE, our
      // own `done` handler above already closed the connection, so this
      // won't keep firing after that.
      eventSource.onerror = () => {
        if (sseConnectTimeoutId) clearTimeout(sseConnectTimeoutId);
        if (stageRef.current >= DONE_STAGE) return;
        eventSource?.close();
        fallBackToPolling();
      };
    }

    try {
      socket = new WebSocket(consensusWsUrl(activeJobId));
    } catch (err) {
      console.error("Consensus WS setup failed, trying SSE instead:", err);
      socket = null;
      fallBackToSse();
    }

    if (socket) {
      wsConnectTimeoutId = setTimeout(() => {
        if (!cancelled && socket && socket.readyState !== WebSocket.OPEN) {
          socket.close();
        }
      }, WS_CONNECT_TIMEOUT_MS);

      socket.onopen = () => {
        if (wsConnectTimeoutId) clearTimeout(wsConnectTimeoutId);
      };

      socket.onmessage = (event) => {
        if (cancelled) return;
        try {
          applyPayload(JSON.parse(event.data));
        } catch (err) {
          console.error("Bad consensus WS payload:", err);
        }
      };

      socket.onerror = () => {
        // onclose always follows in browsers — let that drive the fallback
        // so there's one place deciding whether to move to the next tier.
      };

      socket.onclose = () => {
        if (wsConnectTimeoutId) clearTimeout(wsConnectTimeoutId);
        fallBackToSse();
      };
    }

    return () => {
      cancelled = true;
      if (wsConnectTimeoutId) clearTimeout(wsConnectTimeoutId);
      if (sseConnectTimeoutId) clearTimeout(sseConnectTimeoutId);
      if (pollTimeoutId) clearTimeout(pollTimeoutId);
      socket?.close();
      eventSource?.close();
    };
  }, [jobId]);

  return state;
}
