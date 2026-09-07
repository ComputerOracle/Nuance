// scripts/genlayer-read.ts — Part 2, Step 4 (indexer support).
//
// A thin, read-only RPC bridge to GenLayer Bradbury, invoked as a
// subprocess by backend/app/services/genlayer_indexer.py. Exists because
// this repo has no verified Python GenLayer SDK (genlayer_py isn't
// installed, and scripts/deploy.ts's own header already documents why
// guessing at an unverified SDK's call shape from docs alone repeatedly
// produced real Bradbury failures) — genlayer-js is the one already-
// installed, already-verified client (see deploy.ts and lib/chain-status.ts),
// so the indexer reuses it for the RPC leg instead of re-deriving raw
// JSON-RPC calls in Python from scratch.
//
// Read-only on purpose: every call here is client.readContract/
// getTransaction, neither of which needs (or is passed) an account/private
// key — confirmed directly against the installed .d.ts (readContract's
// `account` param is optional) and live-tested against the real deployed
// NuanceEscrow/NuanceDisputeCourt/NuancePredictionMarket bootstrap
// instances on 2026-09-07 (get_escrow/get_milestone/get_dispute_count/
// get_market all returned clean, already-JSON-safe plain objects with
// jsonSafeReturn: true — no BigInt handling needed on either side of this
// bridge). The indexer never signs or sends a transaction; only
// scripts/deploy.ts and (once built) the frontend's own writeContract call
// hold GENLAYER_PRIVATE_KEY / a wallet.
//
// bucketFromStatusName/isSuccessfulResult are imported straight from
// lib/chain-status.ts rather than re-derived here — that file's own header
// explains why the "which of the 14 raw TransactionStatus values counts as
// decided" list has to come from the SDK's own isDecidedState(), not a
// hand-copied list two files could let drift. The indexer (Python) never
// sees the raw 14-value status directly for bucketing purposes; it gets
// this file's already-bucketed answer, so there is exactly one place in
// the whole repo that computes it.
//
// Protocol: reads one JSON object from stdin —
//   { "reads": [{ "id": string, "address": "0x...", "functionName": string, "args"?: unknown[] }],
//     "transactions": ["0x<hash>", ...] }
// — and writes one JSON object to stdout —
//   { "reads": { [id]: { ok: true, result } | { ok: false, error } },
//     "transactions": { [hash]: { ok: true, rawStatusName, bucket, success, raw } | { ok: false, error } } }
// Every item is caught individually so one bad address/hash can't take
// down the whole batch — same principle as deploy.ts's per-contract error
// handling, just applied per read instead of per deploy.

import { createClient, chains } from "genlayer-js";
import { transactionsStatusNumberToName, type TransactionHash, type TransactionStatus, type TransactionResult as TxResultEnum } from "genlayer-js/types";
import { bucketFromStatusName, isSuccessfulResult, LEGACY_OFFCHAIN, type ChainStatus } from "../lib/chain-status";

interface ReadRequest {
  id: string;
  address: string;
  functionName: string;
  args?: unknown[];
}

interface Request {
  reads?: ReadRequest[];
  transactions?: string[];
}

function safeStringify(value: unknown): string {
  return JSON.stringify(value, (_k, v) => (typeof v === "bigint" ? v.toString() : v));
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// Same field-priority logic as deploy.ts's isAcceptedOrFinalized() (see
// that file's third-round note): the camelCase `statusName` field the
// .d.ts declares was empty on a real live receipt; the real object
// carried a snake_case `status_name` and a numeric `status` instead.
// Checked in that same priority order here, generalized to return
// whichever one is actually populated rather than testing for one value.
function extractStatusName(tx: Record<string, unknown>): TransactionStatus | undefined {
  const camel = tx.statusName as TransactionStatus | undefined;
  const snake = tx.status_name as TransactionStatus | undefined;
  const numeric = typeof tx.status === "number" ? tx.status : undefined;
  return (
    camel ??
    snake ??
    (numeric !== undefined
      ? (transactionsStatusNumberToName as Record<number, TransactionStatus>)[numeric]
      : undefined)
  );
}

function extractResultName(tx: Record<string, unknown>): TxResultEnum | undefined {
  return (
    (tx.txExecutionResultName as TxResultEnum | undefined) ??
    (tx.tx_execution_result_name as TxResultEnum | undefined)
  );
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("utf-8");
}

async function main() {
  const raw = await readStdin();
  const request: Request = raw.trim() ? JSON.parse(raw) : {};

  const client = createClient({ chain: chains.testnetBradbury });

  const reads: Record<string, { ok: true; result: unknown } | { ok: false; error: string }> = {};
  for (const r of request.reads ?? []) {
    try {
      const result = await client.readContract({
        address: r.address as `0x${string}`,
        functionName: r.functionName,
        args: (r.args ?? []) as never,
        jsonSafeReturn: true,
      });
      reads[r.id] = { ok: true, result };
    } catch (err) {
      reads[r.id] = { ok: false, error: errorMessage(err) };
    }
  }

  const transactions: Record<
    string,
    | {
        ok: true;
        rawStatusName: TransactionStatus | undefined;
        bucket: ChainStatus;
        // null (not the same as false/undetermined) until the tx has
        // actually finished executing — see chain-status.ts's own note on
        // isSuccessfulResult: reaching FINALIZED doesn't by itself mean
        // the contract call succeeded.
        success: boolean | null;
        raw: unknown;
      }
    | { ok: false; error: string }
  > = {};
  for (const hash of request.transactions ?? []) {
    try {
      const tx = await client.getTransaction({ hash: hash as TransactionHash });
      const record = tx as unknown as Record<string, unknown>;
      const statusName = extractStatusName(record);
      const resultName = extractResultName(record);
      transactions[hash] = {
        ok: true,
        rawStatusName: statusName,
        bucket: statusName ? bucketFromStatusName(statusName) : (LEGACY_OFFCHAIN as ChainStatus),
        success: resultName === undefined ? null : isSuccessfulResult(resultName),
        raw: tx,
      };
    } catch (err) {
      transactions[hash] = { ok: false, error: errorMessage(err) };
    }
  }

  process.stdout.write(safeStringify({ reads, transactions }));
}

main().catch((err) => {
  // A fatal, batch-level failure (e.g. malformed stdin) — distinct from a
  // per-item error above, which is captured in the output instead of
  // thrown. Exit non-zero so the Python caller can tell the difference
  // between "got a response with some per-item errors" and "got nothing."
  process.stderr.write(`genlayer-read fatal: ${errorMessage(err)}\n`);
  process.exitCode = 1;
});
