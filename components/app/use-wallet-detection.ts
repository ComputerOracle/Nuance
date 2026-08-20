"use client";

import { useEffect, useState } from "react";
import type { Eip1193Provider } from "@/components/app/eip1193";

// EIP-6963 (Multi Injected Provider Discovery) is the standard modern
// browsers/extensions use to announce installed wallets without everyone
// fighting over `window.ethereum`. We request announcements and collect
// each wallet's `rdns` (a reverse-DNS id, e.g. "io.metamask") mapped to its
// actual provider, so we can connect through the specific wallet a user
// clicks rather than an ambiguous global. See
// https://eips.ethereum.org/EIPS/eip-6963.
interface Eip6963ProviderInfo {
  uuid: string;
  name: string;
  rdns: string;
}
interface Eip6963AnnounceEvent extends Event {
  detail: { info: Eip6963ProviderInfo; provider: Eip1193Provider };
}

// A handful of wallets predate/skip EIP-6963 in some contexts (or Phantom's
// Ethereum provider lives at a fixed window property instead). These are
// last-resort direct checks, only used to fill gaps the announce event
// leaves — an extension that supports 6963 always wins via that path.
function legacyDetect(): Map<string, Eip1193Provider> {
  const found = new Map<string, Eip1193Provider>();
  if (typeof window === "undefined") return found;
  const w = window as unknown as {
    ethereum?: Eip1193Provider & { providers?: (Eip1193Provider & Record<string, unknown>)[] } & Record<string, unknown>;
    phantom?: { ethereum?: Eip1193Provider };
  };

  const candidates = w.ethereum ? [w.ethereum, ...(w.ethereum.providers ?? [])] : [];
  for (const p of candidates) {
    if (!p || typeof p !== "object") continue;
    const flags = p as unknown as Record<string, unknown>;
    if (flags.isMetaMask) found.set("io.metamask", p as Eip1193Provider);
    if (flags.isCoinbaseWallet) found.set("com.coinbase.wallet", p as Eip1193Provider);
    if (flags.isTrust || flags.isTrustWallet) found.set("com.trustwallet.app", p as Eip1193Provider);
    if (flags.isRabby) found.set("io.rabby", p as Eip1193Provider);
    if (flags.isOkxWallet || flags.isOKExWallet) found.set("com.okex.wallet", p as Eip1193Provider);
  }
  if (w.phantom?.ethereum) found.set("app.phantom", w.phantom.ethereum);

  return found;
}

export function useWalletDetection(): Map<string, Eip1193Provider> {
  // Lazy initializer runs the legacy synchronous checks once, at mount —
  // not a setState call, so it doesn't trigger the cascading-render lint.
  const [detected, setDetected] = useState<Map<string, Eip1193Provider>>(() => legacyDetect());

  useEffect(() => {
    const seen = legacyDetect();

    function onAnnounce(event: Event) {
      const { detail } = event as Eip6963AnnounceEvent;
      if (!detail?.info?.rdns) return;
      // Always overwrite, even if this rdns slot already has an entry: a
      // self-announced EIP-6963 provider is authoritative and must win over
      // the legacy `isMetaMask`-style guess seeded above. Several wallets
      // (Trust Wallet, Coinbase Wallet, Rabby, ...) set `isMetaMask: true`
      // on their own provider for compatibility with dApps that only check
      // that flag — without this, whichever of those injects first gets
      // permanently misidentified as MetaMask and the real MetaMask's
      // announcement is silently dropped.
      seen.set(detail.info.rdns, detail.provider);
      setDetected(new Map(seen));
    }

    window.addEventListener("eip6963:announceProvider", onAnnounce);
    window.dispatchEvent(new Event("eip6963:requestProvider"));

    return () => {
      window.removeEventListener("eip6963:announceProvider", onAnnounce);
    };
  }, []);

  return detected;
}
