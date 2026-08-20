"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Eip1193Provider } from "@/components/app/eip1193";
import { isEip1193Error } from "@/components/app/eip1193";
import {
  GENLAYER_BRADBURY,
  GENLAYER_BRADBURY_ADD_CHAIN_PARAMS,
} from "@/components/app/genlayer-chain";

export type WalletConnectionStatus = "idle" | "connecting" | "connected";

function formatAddress(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

// wei (hex string from eth_getBalance) -> a display string, done with
// BigInt integer/remainder math rather than Number division so large
// balances don't pick up float rounding error.
function formatNativeBalance(weiHex: string, displayDecimals = 4): string {
  const wei = BigInt(weiHex);
  // BigInt(10) ** n rather than a 10n literal — the project's TS target
  // (ES2017, set by create-next-app for broad output compatibility)
  // predates BigInt literal syntax, though the BigInt() call itself is fine.
  const base = BigInt(10) ** BigInt(GENLAYER_BRADBURY.nativeCurrency.decimals);
  const whole = wei / base;
  const frac = wei % base;
  const fracStr = frac
    .toString()
    .padStart(GENLAYER_BRADBURY.nativeCurrency.decimals, "0")
    .slice(0, displayDecimals);
  return `${whole.toLocaleString("en-US")}.${fracStr}`;
}

// Browser-safe utf8->hex (no Buffer dependency) for personal_sign, which
// expects the message as a hex-encoded string.
function utf8ToHex(str: string): string {
  const bytes = new TextEncoder().encode(str);
  return "0x" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function signInMessage(address: string): string {
  const nonce =
    typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return [
    "Sign in to Nuance",
    "",
    "This request will not trigger a blockchain transaction or cost any gas fees.",
    "",
    `Wallet: ${address}`,
    `Nonce: ${nonce}`,
    `Issued At: ${new Date().toISOString()}`,
  ].join("\n");
}

function describeError(err: unknown): string {
  if (isEip1193Error(err)) {
    if (err.code === 4001) return "Connection request rejected.";
    return err.message || "Wallet request failed.";
  }
  if (err instanceof Error) return err.message;
  return "Wallet request failed.";
}

export function useWalletConnection() {
  const [status, setStatus] = useState<WalletConnectionStatus>("idle");
  const [walletName, setWalletName] = useState("");
  const [address, setAddress] = useState("");
  const [balance, setBalance] = useState("");
  const [chainIdDecimal, setChainIdDecimal] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const providerRef = useRef<Eip1193Provider | null>(null);
  const listenersRef = useRef<{
    onAccountsChanged: (...args: unknown[]) => void;
    onChainChanged: (...args: unknown[]) => void;
  } | null>(null);

  const refreshBalance = useCallback(async (provider: Eip1193Provider, addr: string) => {
    try {
      const weiHex = (await provider.request({
        method: "eth_getBalance",
        params: [addr, "latest"],
      })) as string;
      setBalance(formatNativeBalance(weiHex));
    } catch {
      // Balance is cosmetic — a failed refresh shouldn't drop the connection.
    }
  }, []);

  const teardownListeners = useCallback(() => {
    const provider = providerRef.current;
    const listeners = listenersRef.current;
    if (provider?.removeListener && listeners) {
      provider.removeListener("accountsChanged", listeners.onAccountsChanged);
      provider.removeListener("chainChanged", listeners.onChainChanged);
    }
    listenersRef.current = null;
  }, []);

  const disconnect = useCallback(() => {
    const provider = providerRef.current;
    teardownListeners();
    // EIP-1193 has no universal "disconnect" for injected wallets — most
    // extensions keep the site authorized until the user revokes it
    // themselves. EIP-2255 permission revocation is opt-in per wallet, so
    // this is attempted best-effort and never blocks clearing local state.
    if (provider) {
      provider
        .request({
          method: "wallet_revokePermissions",
          params: [{ eth_accounts: {} }],
        })
        .catch(() => {});
    }
    providerRef.current = null;
    setStatus("idle");
    setWalletName("");
    setAddress("");
    setBalance("");
    setChainIdDecimal(null);
    setError(null);
  }, [teardownListeners]);

  const connect = useCallback(
    async (provider: Eip1193Provider, name: string) => {
      setStatus("connecting");
      setError(null);
      try {
        const accounts = (await provider.request({
          method: "eth_requestAccounts",
        })) as string[];
        const addr = accounts[0];
        if (!addr) throw new Error("No account returned by wallet.");

        // Prove control of the account with a real signature — no
        // transaction, no gas, matching what the connect modal tells the
        // user this step does. Rejecting the signature aborts the
        // connection rather than falling back to an unverified account.
        await provider.request({
          method: "personal_sign",
          params: [utf8ToHex(signInMessage(addr)), addr],
        });

        const chainIdHex = (await provider.request({ method: "eth_chainId" })) as string;

        providerRef.current = provider;
        setWalletName(name);
        setAddress(addr);
        setChainIdDecimal(parseInt(chainIdHex, 16));
        setStatus("connected");
        void refreshBalance(provider, addr);

        const onAccountsChanged = (...args: unknown[]) => {
          const next = args[0] as string[];
          if (!next?.length) {
            disconnect();
            return;
          }
          setAddress(next[0]);
          void refreshBalance(provider, next[0]);
        };
        const onChainChanged = (...args: unknown[]) => {
          const next = args[0] as string;
          setChainIdDecimal(parseInt(next, 16));
          void refreshBalance(provider, addr);
        };
        provider.on?.("accountsChanged", onAccountsChanged);
        provider.on?.("chainChanged", onChainChanged);
        listenersRef.current = { onAccountsChanged, onChainChanged };
        return true;
      } catch (err) {
        providerRef.current = null;
        setStatus("idle");
        setError(describeError(err));
        return false;
      }
    },
    [disconnect, refreshBalance]
  );

  const switchNetwork = useCallback(async () => {
    const provider = providerRef.current;
    if (!provider) return;
    setError(null);
    try {
      await provider.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: GENLAYER_BRADBURY.chainIdHex }],
      });
    } catch (err) {
      // 4902: chain not yet added to the wallet — add it, then switch.
      if (isEip1193Error(err) && err.code === 4902) {
        try {
          await provider.request({
            method: "wallet_addEthereumChain",
            params: [GENLAYER_BRADBURY_ADD_CHAIN_PARAMS],
          });
        } catch (addErr) {
          // A wallet's own "add network" dialog validates the RPC itself
          // before accepting it — if that check fails client-side (a flaky
          // path between the wallet and the RPC, not this app), the wallet's
          // generic error leaves no way forward. Give the manual fallback
          // inline rather than a dead end.
          setError(
            `${describeError(addErr)} You can add the network manually in ` +
              `your wallet: Chain ID ${GENLAYER_BRADBURY.chainIdDecimal}, ` +
              `RPC ${GENLAYER_BRADBURY.rpcUrl}, currency ${GENLAYER_BRADBURY.nativeCurrency.symbol}.`
          );
        }
      } else {
        setError(describeError(err));
      }
    }
  }, []);

  useEffect(() => teardownListeners, [teardownListeners]);

  return {
    status,
    walletName,
    address,
    addressShort: address ? formatAddress(address) : "",
    balance,
    chainIdDecimal,
    isWrongNetwork:
      status === "connected" && chainIdDecimal !== GENLAYER_BRADBURY.chainIdDecimal,
    error,
    connect,
    disconnect,
    switchNetwork,
  };
}
