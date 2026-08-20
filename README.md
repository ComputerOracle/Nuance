# Nuance

Landing page for **Nuance** — "Contracts that understand nuance, not just
logic." AI-validator consensus for claims traditional smart contracts can't
settle: was the work actually good, did the campaign really mislead, who
broke the deal. Built on GenLayer's Testnet Bradbury.

Rebuilt in Next.js from the [Claude Design](https://claude.ai/design) source
canvas (App Router, TypeScript, Tailwind CSS v4, React 19).

## Getting started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Structure

- `app/page.tsx` — assembles the landing page from `components/`.
- `app/app/page.tsx` — the product app: escrows, prediction markets, dispute
  court, governance, validator directory, agent directory, settings, plus a
  wallet-connect flow. All client-side state (mock data, no real chain
  calls), rebuilt 1:1 from the source design's logic.
  - `components/app/nuance-app.tsx` — top-level client component owning all
    app state and view routing.
  - `components/app/views/` — one component per section.
  - `components/app/consensus-panel.tsx` — shared AI-validator-consensus UI
    (used by both the escrow-milestone review and the dispute ruling flow).
  - `components/app/data.ts` / `types.ts` / `status.ts` — mock data, shared
    types, and the status-badge/initials helpers.
  - `components/app/wallet-modal.tsx` + `wallet-catalog.tsx` +
    `use-wallet-detection.ts` — the "Connect a wallet" modal (MetaMask,
    Phantom, Trust Wallet, Rabby, OKX Wallet, Coinbase Wallet). Ready/Install
    status is real: it uses [EIP-6963](https://eips.ethereum.org/EIPS/eip-6963)
    provider discovery (plus legacy `window.ethereum` flag checks) to detect
    which extensions are actually installed in the visitor's browser, with a
    fallback for wallets that predate it. An "Install" card opens that
    wallet's official download page instead of faking a connection.
    `wallet-icons.tsx` holds hand-built brand marks — official asset kits
    aren't fetchable here, so these are original, recognizable stand-ins
    rather than traced logos.
  - `components/app/use-wallet-connection.ts` — the connection itself is
    real, not mocked: `eth_requestAccounts` → a `personal_sign` signature
    (proving key control, matching the modal's "Sign-in only" promise) →
    `eth_chainId` → `eth_getBalance`, plus live `accountsChanged` /
    `chainChanged` subscriptions. `genlayer-chain.ts` holds GenLayer Testnet
    Bradbury's actual network params (chain id `4221` / `0x107d`, RPC,
    native currency `GEN`) sourced from the official
    [genlayer-js](https://github.com/genlayerlabs/genlayer-js) SDK, used to
    detect a wrong network and drive `wallet_switchEthereumChain` /
    `wallet_addEthereumChain`. The sidebar's address and balance are the
    real connected values — only the escrow/prediction/dispute dollar
    amounts elsewhere in the app remain demo data, as they were before.
- `app/globals.css` — design tokens (`@theme`) matching the source design's
  oklch palette, plus shared keyframes (`fadeUp`, `spin`, `pulse-dot`).
- `components/consensus-demo.tsx` — the interactive "AI Validator Consensus"
  hero widget on the landing page (client component): clicking **Run
  consensus** steps three validators through Queued → Analyzing → Consensus
  recorded, then reveals the verdict panel.
- `components/logo.tsx` — hand-built SVG brand mark. The source design's
  PNG logo/icon assets couldn't be fetched in full (truncated by a 256KB
  read cap on a larger file) — replace with the real asset when available.

## Notes

- Colors are authored as `oklch()` to match the source 1:1; Tailwind v4
  emits sRGB fallbacks automatically for browsers without `oklch` support.
- Any project-wide `a { ... }` (or similar unlayered) rule in `globals.css`
  must live inside `@layer base` — Tailwind v4's utilities are cascade
  layers, and unlayered CSS beats them regardless of specificity.
