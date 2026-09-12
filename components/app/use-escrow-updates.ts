"use client";

import { useEffect, useState } from "react";
import type { ApiEscrow } from "@/lib/api";

// Same cadence/timeouts as use-dispute-messages.ts's own constants — one
// established, already-proven-live tuning for this app's WS/SSE/polling
// chain, not a second one to keep in sync by hand.
const POLL_INTERVAL_MS = 3000;
const WS_CONNECT_TIMEOUT_MS = 1500;
const SSE_CONNECT_TIMEOUT_MS = 1500;

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010";
}

function escrowWsUrl(escrowId: number): string {
  return `${apiBase().replace(/^http/, "ws")}/escrows/ws/${escrowId}`;
}

function escrowSseUrl(escrowId: number): string {
  return `${apiBase()}/escrows/sse/${escrowId}`;
}

type EscrowPayload = { type: "escrow"; escrow: ApiEscrow };
type ErrorPayload = { error: string };
type ChannelPayload = EscrowPayload | ErrorPayload;

/**
 * Live counterpart to `getEscrow` (lib/api.ts) — added 2026-09-12 after a
 * real gap found live: an already-open escrow detail view had no way to
 * learn that a background auto-deploy had just linked a contract (or any
 * other server-side change — funding, a milestone's consensus verdict
 * landing, an on-chain sync from services/genlayer_indexer.py) short of a
 * manual page reload. Same WS -> SSE -> polling chain use-consensus-
 * polling.ts / use-dispute-messages.ts already established for their own
 * channels (backend/app/routers/escrows.py's `escrow_updates_ws`/
 * `escrow_updates_sse`).
 *
 * Unlike dispute messages (an append-only list, deduped by id), an
 * escrow's state is one mutable record — every tick/publish carries the
 * FULL current snapshot, so this hook just returns the latest one
 * wholesale rather than reconciling a delta. The caller (nuance-app.tsx)
 * merges it into its own `escrows` array, same as any other single-
 * escrow refetch already does (mapEscrow + replace-by-id).
 *
 * No terminal state here either — an escrow keeps changing for its whole
 * lifetime, so this stays connected for as long as `escrowId` is set and
 * the component is mounted.
 */
export function useEscrowUpdates(escrowId: number | null): ApiEscrow | null {
  const [escrow, setEscrow] = useState<ApiEscrow | null>(null);

  // Reset synchronously when escrowId changes (not via setState inside
  // the effect below) — same "adjust state during render" reasoning use-
  // dispute-messages.ts/use-consensus-polling.ts already document:
  // otherwise a previously-viewed escrow's stale snapshot would flash
  // before the newly-selected escrow's own first payload arrives.
  const [trackedEscrowId, setTrackedEscrowId] = useState(escrowId);
  if (escrowId !== trackedEscrowId) {
    setTrackedEscrowId(escrowId);
    setEscrow(null);
  }

  useEffect(() => {
    if (escrowId == null) return;
    const activeEscrowId = escrowId;

    let cancelled = false;
    let pollTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let wsConnectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let sseConnectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    let socket: WebSocket | null = null;
    let eventSource: EventSource | null = null;
    let polling = false;
    let sseStarted = false;

    function applyPayload(payload: ChannelPayload) {
      if (cancelled) return;
      if ("error" in payload) return; // escrow not found (yet) — wait for a real tick or the close below
      setEscrow(payload.escrow);
    }

    async function pollTick() {
      try {
        const resp = await fetch(`${apiBase()}/escrows/${activeEscrowId}`);
        if (resp.ok) {
          const data = (await resp.json()) as ApiEscrow;
          if (!cancelled) setEscrow(data);
        }
      } catch (err) {
        if (!cancelled) console.error("Escrow updates poll failed:", err);
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
        eventSource = new EventSource(escrowSseUrl(activeEscrowId));
      } catch (err) {
        console.error("Escrow updates SSE setup failed, polling instead:", err);
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
          console.error("Bad escrow updates SSE payload:", err);
        }
      };

      eventSource.onerror = () => {
        if (sseConnectTimeoutId) clearTimeout(sseConnectTimeoutId);
        eventSource?.close();
        fallBackToPolling();
      };
    }

    try {
      socket = new WebSocket(escrowWsUrl(activeEscrowId));
    } catch (err) {
      console.error("Escrow updates WS setup failed, trying SSE instead:", err);
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
          console.error("Bad escrow updates WS payload:", err);
        }
      };

      socket.onerror = () => {
        // onclose always follows in browsers — let that drive the
        // fallback so there's one place deciding whether to move on.
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
  }, [escrowId]);

  return escrow;
}
