// scripts/verify-real-consensus.ts — proves real GenVM validator
// consensus actually works end to end on live Bradbury, not just that
// this app's code *would* call it correctly.
//
// Why this exists: an audit of the running app (2026-09-08) found that
// while the on-chain wiring is real and reachable (submit_deliverable_
// on_chain, adjudicate_dispute, resolve_market all issue real
// writeContract calls when a row is linked to a deployed contract), almost
// nothing in the live database actually IS linked, and — critically —
// nobody had ever confirmed a submit_deliverable call actually completes
// real multi-validator equivalence-principle consensus on Bradbury. Every
// existing "proof" in this codebase's own comments is about deploys
// succeeding, not about a nondet consensus call succeeding.
//
// What this script actually does, with no wallet/browser needed and no
// risk to anyone's real funds:
//   1. Deploys a fresh, disposable NuanceEscrow using this app's own
//      backend deployer key (GENLAYER_PRIVATE_KEY, backend/.env) — the
//      exact same key/engine services/genlayer_deploy.py already uses in
//      production, not a special test path.
//   2. Sets BOTH creator and counterparty to that same deployer address,
//      deliberately — this script only needs to prove the *validator
//      consensus* mechanism works, not exercise the separate creator-vs-
//      counterparty authorization logic (already covered by this app's
//      own pytest suite). One self-signed account means no second wallet
//      or real fund transfer is needed at all: submit_deliverable isn't
//      payable, so nothing but gas is ever spent.
//   3. Calls submit_deliverable() with a real deliverable, signed by that
//      same key, and waits for the transaction to actually reach
//      ACCEPTED — the real GenVM stage at which the equivalence principle
//      (gl.vm.run_nondet_unsafe in contracts/nuance_escrow.py's
//      submit_deliverable) has already run: the leader validator proposed
//      an approve/dispute decision, and the other validators in the
//      committee each independently re-ran the same LLM judgment and had
//      to agree before the network would accept the transaction at all.
//   4. Reads back get_milestone(0) afterward and prints the recorded
//      status/reasoning — text that only exists because that consensus
//      round actually happened, not something this script or the backend
//      computed itself.
//
// Run it: `npx tsx scripts/verify-real-consensus.ts` from the repo root.
// Takes a few minutes (real Bradbury deploy + a real nondet consensus
// round, same order of magnitude as any other deploy in this codebase).

import { createAccount, createClient, chains } from "genlayer-js";
import { TransactionStatus, type TransactionHash } from "genlayer-js/types";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { deployOne, withRateLimitRetry, REPO_ROOT } from "./genlayer-deploy-core";

const BACKEND_ENV_PATH = resolve(REPO_ROOT, "backend/.env");

function loadEnvFile(path: string): void {
  if (existsSync(path)) process.loadEnvFile(path);
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

async function main() {
  loadEnvFile(BACKEND_ENV_PATH);
  const privateKey = process.env.GENLAYER_PRIVATE_KEY;
  if (!privateKey) {
    console.error(`✗ GENLAYER_PRIVATE_KEY not set in ${BACKEND_ENV_PATH} — nothing to sign with.`);
    process.exitCode = 1;
    return;
  }

  const account = createAccount(privateKey as `0x${string}`);
  const client = createClient({ chain: chains.testnetBradbury, account });

  console.log(`Deployer/self-test address: ${account.address}`);
  console.log("Step 1/3 — deploying a fresh, disposable NuanceEscrow…");

  const deliverableText =
    "Real end-to-end verification run by scripts/verify-real-consensus.ts on " +
    new Date().toISOString() +
    ". Criteria: this deliverable text must describe a completed verification task.";

  let contractAddress: string;
  try {
    contractAddress = await deployOne(client, {
      name: "verify-real-consensus escrow",
      file: "nuance_escrow.py",
      args: [
        account.address, // creator
        account.address, // counterparty — same account, see header
        "Verification Milestone",
        1, // milestone_amount, u256 — trivial; this run never calls fund_escrow/release_milestone
        "Deliverable text must describe a completed verification task.",
      ],
    });
  } catch (err) {
    console.error(`✗ Deploy failed: ${errorMessage(err)}`);
    process.exitCode = 1;
    return;
  }
  console.log(`  Deployed: ${contractAddress}`);

  console.log("Step 2/3 — calling submit_deliverable() and waiting for real validator consensus…");
  let txHash: string;
  try {
    txHash = String(
      await withRateLimitRetry("submit_deliverable writeContract", () =>
        client.writeContract({
          address: contractAddress as `0x${string}`,
          functionName: "submit_deliverable",
          args: [0, deliverableText, ""] as never,
          value: BigInt(0),
        })
      )
    );
  } catch (err) {
    console.error(`✗ submit_deliverable call failed to send: ${errorMessage(err)}`);
    process.exitCode = 1;
    return;
  }
  console.log(`  Sent: ${txHash}`);

  let receipt;
  try {
    // Same 60x3s wait deployOne uses — a nondet consensus round (the
    // leader's LLM call, then every other validator independently
    // re-running it) is not necessarily faster than a deploy.
    receipt = await withRateLimitRetry("submit_deliverable waitForTransactionReceipt", () =>
      client.waitForTransactionReceipt({
        hash: txHash as TransactionHash,
        status: TransactionStatus.ACCEPTED,
        retries: 60,
        interval: 3000,
      })
    );
  } catch (err) {
    console.error(`✗ Transaction never reached ACCEPTED: ${errorMessage(err)}`);
    console.error(`  Contract: ${contractAddress}  Tx: ${txHash}`);
    process.exitCode = 1;
    return;
  }
  console.log(`  Status: ${receipt.statusName ?? receipt.status} — real GenVM validator committee has decided.`);

  console.log("Step 3/3 — reading back the recorded verdict…");
  let milestone: { status?: string; reasoning?: string } | undefined;
  try {
    milestone = (await client.readContract({
      address: contractAddress as `0x${string}`,
      functionName: "get_milestone",
      args: [0] as never,
      jsonSafeReturn: true,
    })) as { status?: string; reasoning?: string };
  } catch (err) {
    console.error(`✗ Deployed and consensus completed, but couldn't read back the result: ${errorMessage(err)}`);
    console.error(`  Contract: ${contractAddress}  Tx: ${txHash}`);
    process.exitCode = 1;
    return;
  }

  console.log("");
  console.log("=== VERIFIED: real GenVM validator consensus ran on live Bradbury ===");
  console.log(`Contract:        ${contractAddress}`);
  console.log(`Tx hash:         ${txHash}`);
  console.log(`Milestone status: ${milestone?.status ?? "(missing)"}`);
  console.log(`Validator reasoning: ${milestone?.reasoning ?? "(missing)"}`);
  console.log("");
  console.log(
    "This status/reasoning came from the equivalence-principle consensus round " +
      "(contracts/nuance_escrow.py's submit_deliverable -> gl.vm.run_nondet_unsafe), " +
      "not from this script or Nuance's own backend."
  );

  if (!milestone?.status || !milestone?.reasoning) {
    console.error("✗ Missing status/reasoning on the readback — treat this run as inconclusive, not passed.");
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(`Fatal: ${errorMessage(err)}`);
  process.exitCode = 1;
});
