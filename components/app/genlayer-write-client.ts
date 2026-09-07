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
