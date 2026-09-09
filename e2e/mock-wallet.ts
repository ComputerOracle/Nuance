import type { Page } from "@playwright/test";
import { privateKeyToAccount } from "viem/accounts";

// Hardhat/Anvil's well-known default Account #0 — a publicly documented
// test-only key with no real funds anywhere, used across countless
// open-source projects for exactly this purpose. Never use a real key here.
const TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
const TEST_ACCOUNT = privateKeyToAccount(TEST_PRIVATE_KEY);

/**
 * Installs a fake EIP-6963-announced wallet (components/app/use-wallet-
 * detection.ts) into `page`, before any app script runs, so the "Connect
 * Wallet" flow (components/app/wallet-modal.tsx) finds a real "MetaMask"
 * entry and can drive the actual connect/sign flow end to end — no
 * mocked API responses, no monkeypatched React state.
 *
 * The one real cryptographic operation the app performs client-side is
 * `personal_sign` (use-wallet-connection.ts's SIWE-style login — see
 * that file's own `connect` callback), which a page-injected script
 * can't do on its own (no secp256k1 in the browser's Web Crypto API).
 * `page.exposeFunction` bridges that specific call back to real Node-
 * side signing via viem's `privateKeyToAccount` — every other EIP-1193
 * method the app calls (eth_requestAccounts, eth_chainId, eth_getBalance,
 * wallet_switchEthereumChain, ...) is answered entirely inside the page
 * with fixed values, no round trip needed.
 *
 * Returns the mock wallet's checksummed address.
 */
export async function installMockWallet(page: Page): Promise<string> {
  // Must be registered before addInitScript/goto — Playwright makes an
  // exposeFunction binding available to every subsequent navigation's
  // very first script, which is what lets the init script below call it
  // synchronously-from-the-page's-perspective (it's actually an async
  // round trip to this Node process, but the page just awaits it).
  await page.exposeFunction("__e2eSignRaw", async (hexMessage: `0x${string}`) => {
    return TEST_ACCOUNT.signMessage({ message: { raw: hexMessage } });
  });

  await page.addInitScript(
    ({ address, chainIdHex }) => {
      type Listener = (...args: unknown[]) => void;
      const listeners: Record<string, Listener[]> = {};
      // A comfortably large balance (1000 GEN in wei) — this app never
      // sends a real payable transaction through this mock (escrow auto-
      // deploy is disabled for this test run, see playwright.config.ts),
      // so the exact figure only matters for the sidebar's own display.
      const BALANCE_WEI_HEX = "0x3635c9adc5dea00000";

      const provider = {
        isMetaMask: true,
        async request({ method, params }: { method: string; params?: unknown[] | object }) {
          const args = Array.isArray(params) ? params : [];
          switch (method) {
            case "eth_requestAccounts":
            case "eth_accounts":
              return [address];
            case "eth_chainId":
              return chainIdHex;
            case "eth_getBalance":
              return BALANCE_WEI_HEX;
            case "wallet_switchEthereumChain":
            case "wallet_addEthereumChain":
            case "wallet_revokePermissions":
              return null;
            case "personal_sign": {
              const hexMessage = args[0] as `0x${string}`;
              // Declared for TS in this browser-context callback below.
              return await (window as unknown as { __e2eSignRaw: (m: string) => Promise<string> })
                .__e2eSignRaw(hexMessage);
            }
            default:
              throw { code: 4200, message: `Mock wallet: unsupported method ${method}` };
          }
        },
        on(event: string, handler: Listener) {
          (listeners[event] ??= []).push(handler);
        },
        removeListener(event: string, handler: Listener) {
          listeners[event] = (listeners[event] ?? []).filter((h) => h !== handler);
        },
      };

      const info = {
        uuid: "e2e-mock-wallet-0000-0000-000000000000",
        name: "MetaMask",
        rdns: "io.metamask",
        icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>",
      };

      function announce() {
        window.dispatchEvent(
          new CustomEvent("eip6963:announceProvider", {
            detail: Object.freeze({ info, provider }),
          })
        );
      }

      // use-wallet-detection.ts dispatches "eip6963:requestProvider" on
      // mount and listens for the announce event — this covers that.
      // Announcing once immediately too matches how a real extension
      // announces on injection, not only on request (belt and braces;
      // costs nothing since nobody's listening yet at this exact instant
      // anyway — this script runs before the page's own React tree mounts).
      window.addEventListener("eip6963:requestProvider", announce);
      announce();
    },
    { address: TEST_ACCOUNT.address, chainIdHex: "0x107d" }
  );

  return TEST_ACCOUNT.address;
}
