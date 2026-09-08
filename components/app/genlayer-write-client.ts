// Wallet-signed on-chain writes — Part 2, Step 4 (ROADMAP.md 4.6).
//
// Every call here goes straight from this browser to the GenLayer
// contract via the user's own connected wallet — never through the
// backend, never with a private key this app holds (that's scripts/
// deploy.ts's job, server-side, deploying new instances — a completely
// different action from calling a method on one that's already live).
// This file does not wait for the transaction to be accepted/finalized
// either; that's services/genlayer_indexer.py's job, polling server-side.
// The caller (components/app/nuance-app.tsx) only needs the tx hash back,
// to hand to POST /escrows/{id}/deliverable/on-chain so the indexer knows
// to watch it.
//
// --- Verification ---
// createClient's browser-wallet shape (account: the connected address,
// provider: the EIP-1193 provider) is ROADMAP.md 4.6's own documented
// pattern, verified there against the installed genlayer-js@1.1.8 type
// definitions. writeContract's return value specifically — a plain
// 0x-prefixed transaction hash string, not a receipt object, despite the
// installed .d.ts loosely typing it as `Promise<any>` — was confirmed by
// reading the installed package's own compiled source directly
// (node_modules/genlayer-js/dist/index.js): writeContract's doc comment
// there reads "Returns the transaction hash," and it delegates to the
// exact same internal _sendTransaction helper deployContract uses —
// which scripts/deploy.ts already proved, against live Bradbury, resolves
// to a plain hash. Not live-tested from *this* file specifically — doing
// so would mean actually signing and sending a real transaction against
// the live bootstrap contract, a mutating action this file's own author
// (an agent, not the person who'll actually use a wallet here) has no
// business doing unprompted. Re-verify against whatever genlayer-js
// version is installed before trusting this again if it's ever upgraded.

import { createClient, chains } from "genlayer-js";
import type { Eip1193Provider } from "@/components/app/eip1193";
import { isEip1193Error } from "@/components/app/eip1193";
import { milliGenToWei, parseGenToWei } from "@/components/app/genlayer-chain";

export interface SubmitDeliverableOnChainArgs {
  walletAddress: string;
  provider: Eip1193Provider;
  contractAddress: `0x${string}`;
  milestoneIndex: number;
  deliverableText: string;
  deliverableUrl: string;
}

export interface FileDisputeOnChainArgs {
  walletAddress: string;
  provider: Eip1193Provider;
  // NuanceDisputeCourt's own address — the one global shared registry
  // (lib/chain-config.ts's disputeCourtContractAddress()), NOT the
  // escrow's own contract_address. See that contract's header: unlike
  // NuanceEscrow, every dispute across the whole app lives in this one
  // instance.
  disputeCourtAddress: `0x${string}`;
  // The escrow's own deployed NuanceEscrow address — file_dispute's first
  // argument, which the contract stores as escrow_address on the dispute
  // record. This is what services/genlayer_indexer.py's
  // resolve_pending_dispute_ids later matches against.
  escrowAddress: `0x${string}`;
  respondentAddress: string;
  claimStatement: string;
  evidenceUrl: string;
}

/** User-facing message for a failed on-chain submit — same style as
 * use-wallet-connection.ts's describeError, reused rather than
 * duplicated logic (isEip1193Error is the same check), separate function
 * because the messages that make sense here ("rejected the transaction")
 * differ from a connection/signing failure's. */
export function describeWriteError(err: unknown): string {
  if (isEip1193Error(err)) {
    if (err.code === 4001) return "Transaction rejected in wallet.";
    return err.message || "Wallet transaction failed.";
  }
  if (err instanceof Error) return err.message;
  return "Wallet transaction failed.";
}

function createWriteClient(walletAddress: string, provider: Eip1193Provider) {
  return createClient({
    chain: chains.testnetBradbury,
    account: walletAddress as `0x${string}`,
    // EthereumProvider isn't resolvable from genlayer-js's own installed
    // .d.ts (a real gap in this pre-mainnet SDK's types, confirmed via
    // `tsc --noEmit` on this exact file — not this project's bug to fix)
    // — cast rather than fight a type name the package itself can't
    // resolve. The runtime shape genlayer-js actually needs (a `request`
    // method) is exactly what Eip1193Provider already guarantees.
    provider: provider as never,
  });
}

// BigInt(0), not a `0n` literal, everywhere below — this project's TS
// target (ES2017) predates BigInt literal syntax, same reasoning use-
// wallet-connection.ts's formatNativeBalance already documents.
const ZERO_VALUE = BigInt(0);

/** Signs and sends a real NuanceEscrow.submit_deliverable transaction
 * through the connected wallet. Resolves to the transaction hash — throws
 * (via describeWriteError-translatable errors) on rejection or an RPC
 * failure, same as any other wallet.request call this app already makes. */
export async function submitDeliverableOnChain(
  args: SubmitDeliverableOnChainArgs
): Promise<string> {
  const client = createWriteClient(args.walletAddress, args.provider);

  const txHash = await client.writeContract({
    address: args.contractAddress,
    functionName: "submit_deliverable",
    args: [args.milestoneIndex, args.deliverableText, args.deliverableUrl] as never,
    value: ZERO_VALUE,
  });

  return String(txHash);
}

/** Signs and sends a real NuanceDisputeCourt.file_dispute transaction
 * through the connected wallet. Resolves to the transaction hash — NOT
 * the dispute id the contract assigns internally; genlayer-js has no
 * documented way to decode a regular write call's return value (only a
 * deploy's — see scripts/deploy.ts's extractDeployedAddress). The caller
 * hands this hash to POST /escrows/{id}/dispute/on-chain, which creates
 * the local Dispute row with on_chain_dispute_id left null;
 * services/genlayer_indexer.py's resolve_pending_dispute_ids fills it in
 * asynchronously by matching (claimant, escrow_address, claim_statement)
 * against the contract's own history once the tx lands — see that
 * function's docstring for the full reasoning. `claimStatement` here
 * MUST be passed through to that ack endpoint's `issue` field verbatim
 * (exact string equality is what the indexer matches on). */
export async function fileDisputeOnChain(args: FileDisputeOnChainArgs): Promise<string> {
  const client = createWriteClient(args.walletAddress, args.provider);

  const txHash = await client.writeContract({
    address: args.disputeCourtAddress,
    functionName: "file_dispute",
    args: [
      args.escrowAddress,
      args.respondentAddress,
      args.claimStatement,
      args.evidenceUrl,
    ] as never,
    value: ZERO_VALUE,
  });

  return String(txHash);
}

export interface BetOnChainArgs {
  walletAddress: string;
  provider: Eip1193Provider;
  contractAddress: `0x${string}`;
  outcome: "YES" | "NO";
  // Milli-GEN (1000 = 1 GEN) — one of the fixed quick-pick presets
  // (backend/app/schemas/core.py's BET_AMOUNTS_MILLI_GEN: 500/1000/2000/
  // 3000 = 0.5/1/2/3 GEN), never free-typed. Converted to real wei via
  // milliGenToWei — an exact integer multiplication, not a floating-point
  // guess — before being sent as this call's actual `value`.
  amountMilliGen: number;
}

export interface ResolveMarketOnChainArgs {
  walletAddress: string;
  provider: Eip1193Provider;
  contractAddress: `0x${string}`;
}

export interface ClaimWinningsOnChainArgs {
  walletAddress: string;
  provider: Eip1193Provider;
  contractAddress: `0x${string}`;
}

export interface FundEscrowOnChainArgs {
  walletAddress: string;
  provider: Eip1193Provider;
  contractAddress: `0x${string}`;
  // The escrow's total, as the backend's own Decimal-serialized string
  // (e.g. "2.50") or a plain number — converted to real wei via
  // parseGenToWei (string-based fixed-point math, not floating-point)
  // before being sent as this call's actual `value`.
  amountGen: number | string;
}

/** Signs and sends a real NuancePredictionMarket.bet transaction through
 * the connected wallet. The one *payable* call in this file — bet()
 * requires gl.message.value > 0 on the contract side, unlike every other
 * write here, which all send value: 0. See BetOnChainArgs.amount's own
 * comment on the wei mapping. Resolves to the transaction hash; the
 * caller hands it to POST /predictions/{id}/bet/on-chain, which mirrors
 * the stake into a PredictionPosition row (see that endpoint's own
 * docstring on why — the indexer's view-sync doesn't track individual
 * bettors' on-chain stakes, only the market's own state as a whole). */
export async function betOnChain(args: BetOnChainArgs): Promise<string> {
  const client = createWriteClient(args.walletAddress, args.provider);

  const txHash = await client.writeContract({
    address: args.contractAddress,
    functionName: "bet",
    args: [args.outcome] as never,
    value: milliGenToWei(args.amountMilliGen),
  });

  return String(txHash);
}

/** Signs and sends a real NuancePredictionMarket.resolve_market
 * transaction. Has no sender restriction on the contract side (anyone can
 * trigger it) — services/genlayer_indexer.py's trigger_pending_market_
 * resolutions already does this automatically, server-side, once a
 * market's cutoff passes, so this is a manual/optional path (e.g. the
 * existing "Resolve Market" button, for someone who doesn't want to wait
 * for the indexer's own poll cycle), not the primary mechanism. */
export async function resolveMarketOnChain(args: ResolveMarketOnChainArgs): Promise<string> {
  const client = createWriteClient(args.walletAddress, args.provider);

  const txHash = await client.writeContract({
    address: args.contractAddress,
    functionName: "resolve_market",
    args: [] as never,
    value: ZERO_VALUE,
  });

  return String(txHash);
}

/** Signs and sends a real NuancePredictionMarket.claim_winnings
 * transaction — pull-based, each bettor claims their own share
 * individually (see that method's own contract-side docstring). This is
 * the ONLY way a winning on-chain bet actually pays out; nothing
 * server-side ever calls this on a bettor's behalf. */
export async function claimWinningsOnChain(args: ClaimWinningsOnChainArgs): Promise<string> {
  const client = createWriteClient(args.walletAddress, args.provider);

  const txHash = await client.writeContract({
    address: args.contractAddress,
    functionName: "claim_winnings",
    args: [] as never,
    value: ZERO_VALUE,
  });

  return String(txHash);
}

/** Signs and sends a real, *payable* NuanceEscrow.fund_escrow
 * transaction — real GEN leaves the creator's wallet and sits in the
 * deployed contract's balance from here on; release_milestone checks
 * this same on-chain funded_amount before it will pay anyone out. Only
 * the escrow creator may call fund_escrow (see that method's own
 * contract-side source) — this file doesn't enforce that itself, the
 * contract does, the same way every other write here relies on the
 * contract's own checks rather than duplicating them client-side. */
export async function fundEscrowOnChain(args: FundEscrowOnChainArgs): Promise<string> {
  const client = createWriteClient(args.walletAddress, args.provider);

  const txHash = await client.writeContract({
    address: args.contractAddress,
    functionName: "fund_escrow",
    args: [] as never,
    value: parseGenToWei(args.amountGen),
  });

  return String(txHash);
}
