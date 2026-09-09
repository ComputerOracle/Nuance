"use client";

import { useEffect, useMemo, useState } from "react";
import { getDisputeMessages, type ApiDisputeMessage } from "@/lib/api";

// Matches dispute-detail-view.tsx's old setInterval cadence exactly — this
// tier only runs at all when neither WS nor SSE ever connected, so keeping
// it identical to the pre-2026-09-08 behavior means a fully-blocked network
// degrades to exactly what shipped before this hook existed, not something
// new and untested.
const POLL_INTERVAL_MS = 3000;
const WS_CONNECT_TIMEOUT_MS = 1500;
const SSE_CONNECT_TIMEOUT_MS = 1500;

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010";
}

function messagesWsUrl(disputeId: number): string {
  return `${apiBase().replace(/^http/, "ws")}/disputes/ws/${disputeId}/messages`;
}

function messagesSseUrl(disputeId: number): string {
  return `${apiBase()}/disputes/sse/${disputeId}/messages`;
}

type InitPayload = { type: "init"; messages: ApiDisputeMessage[] };
type MessagePayload = { type: "message"; message: ApiDisputeMessage };
type ErrorPayload = { error: string };
type ChannelPayload = InitPayload | MessagePayload | ErrorPayload;

/**
 * Live counterpart to `getDisputeMessages`/`sendDisputeMessage` (lib/api.ts)
 * — added 2026-09-08 (ROADMAP.md Part 3 5.2's "live dispute-message
 * updates over the same realtime channel") to replace dispute-detail-
 * view.tsx's old 3s `setInterval` poll with the same WS -> SSE -> polling
 * chain use-consensus-polling.ts already established for the consensus
 * channel (backend/app/routers/disputes.py's `dispute_messages_ws`/
 * `dispute_messages_sse`).
 *
 * Unlike consensus, a dispute's chat has no terminal "DONE" state — this
 * stays connected for as long as `disputeId` is set and the component is
 * mounted, same as the old poll did.
 *
 * `addOptimistic` lets the caller (a just-sent message's own POST response)
 * show up immediately rather than waiting on the round trip through the
 * realtime channel; messages are deduped by id, so the authoritative push
 * that follows (see routers/disputes.py's send_message, which publishes
 * right after commit) is a harmless no-op once it arrives, not a
 * duplicate.
 */
export function useDisputeMessages(disputeId: number | null): {
  messages: ApiDisputeMessage[];
  addOptimistic: (message: ApiDisputeMessage) => void;
} {
  const [messagesById, setMessagesById] = useState<Map<number, ApiDisputeMessage>>(new Map());

  // Reset synchronously when disputeId changes, rather than via setState
  // inside the effect below — matches use-consensus-polling.ts's own
  // "adjust state during render" pattern for the exact same need
  // (otherwise a previously-viewed dispute's messages would flash before
  // the new dispute's own `init` payload arrives). setState-in-effect
  // would cause an extra cascading render — eslint's react-hooks/set-
  // state-in-effect rule (CI-gated, see .github/workflows/ci.yml) flags
  // exactly that.
  const [trackedDisputeId, setTrackedDisputeId] = useState(disputeId);
  if (disputeId !== trackedDisputeId) {
    setTrackedDisputeId(disputeId);
    setMessagesById(new Map());
  }

  useEffect(() => {
    if (disputeId == null) return;
    // A const alias, not the raw parameter — same reasoning as use-
    // consensus-polling.ts's activeJobId: TS discards narrowing across
    // closure boundaries for a mutable parameter, and the nested
    // fallBackToSse/pollTick functions below need disputeId to still
    // read as `number`, not `number | null`.
    const activeDisputeId = disputeId;

    let cancelled = false;
    let pollTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let wsConnectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let sseConnectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;
    let eventSource: EventSource | null = null;
    let polling = false;
    let sseStarted = false;

    function upsert(message: ApiDisputeMessage) {
      if (cancelled) return;
      setMessagesById((prev) => {
        if (prev.has(message.id)) return prev; // already have it (optimistic add, or a repeat tick)
        const next = new Map(prev);
        next.set(message.id, message);
        return next;
      });
    }

    function setAll(messages: ApiDisputeMessage[]) {
      if (cancelled) return;
      setMessagesById(new Map(messages.map((m) => [m.id, m])));
    }

    function applyPayload(payload: ChannelPayload) {
      if ("error" in payload) return; // dispute not found (yet) — wait for a real tick or the close below
      if (payload.type === "init") setAll(payload.messages);
      else upsert(payload.message);
    }

    async function pollTick() {
      try {
        const data = await getDisputeMessages(activeDisputeId);
        if (!cancelled) setAll(data);
      } catch (err) {
        if (!cancelled) console.error("Dispute messages poll failed:", err);
      }
      if (!cancelled) {
        pollTimeoutId = setTimeout(pollTick, POLL_INTERVAL_MS);
      }
    }

    function fallBackToPolling() {
      if (polling || cancelled) return;
      polling = true;
      void pollTick();
    }

    function fallBackToSse() {
      if (sseStarted || cancelled) return;
      sseStarted = true;

      try {
        eventSource = new EventSource(messagesSseUrl(activeDisputeId));
      } catch (err) {
        console.error("Dispute messages SSE setup failed, polling instead:", err);
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

      eventSource.onmessage = (event) => {
        if (cancelled) return;
        try {
          applyPayload(JSON.parse(event.data));
        } catch (err) {
          console.error("Bad dispute messages SSE payload:", err);
        }
      };

      // No named "done" event here (unlike the consensus channel) — a
      // dispute's chat never finishes, so every drop is a real drop.
      eventSource.onerror = () => {
        if (sseConnectTimeoutId) clearTimeout(sseConnectTimeoutId);
        eventSource?.close();
        fallBackToPolling();
      };
    }

    try {
      socket = new WebSocket(messagesWsUrl(activeDisputeId));
    } catch (err) {
      console.error("Dispute messages WS setup failed, trying SSE instead:", err);
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
          console.error("Bad dispute messages WS payload:", err);
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
  }, [disputeId]);

  const messages = useMemo(
    () => Array.from(messagesById.values()).sort((a, b) => a.id - b.id),
    [messagesById]
  );

  function addOptimistic(message: ApiDisputeMessage) {
    setMessagesById((prev) => {
      if (prev.has(message.id)) return prev;
      const next = new Map(prev);
      next.set(message.id, message);
      return next;
    });
  }

  return { messages, addOptimistic };
}
