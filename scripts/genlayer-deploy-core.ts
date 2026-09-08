// scripts/genlayer-deploy-core.ts
//
// The verified GenVM deploy engine, extracted from scripts/deploy.ts so it
// can be shared with scripts/genlayer-deploy.ts (the stdin/stdout bridge
// backend/app/services/genlayer_deploy.py invokes to deploy a real
// NuanceEscrow instance per new escrow) without duplicating the hard-won
// fixes in deployOne/extractDeployedAddress/isAcceptedOrFinalized — see
// deploy.ts's own header for the five rounds of real live-Bradbury
// debugging that produced them. Behavior is unchanged from what deploy.ts
// already had; this is a mechanical extraction, re-verified by confirming
// `npm run deploy:contracts` still type-checks and runs identically
// against the same call shape afterward.

import {
  TransactionStatus,
  ExecutionResult,
  transactionsStatusNameToNumber,
  type GenLayerTransaction,
  type TransactionHash,
  type DecodedDeployData,
} from "genlayer-js/types";
import type { createClient } from "genlayer-js";
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = resolve(__dirname, "..");
export const CONTRACTS_DIR = resolve(REPO_ROOT, "contracts");

// Bradbury's observed rate-limit error code, and how long to back off —
// see deploy.ts's header, "Rate limiting" paragraph.
const RATE_LIMIT_ERROR_CODE = -32005;
const RATE_LIMIT_BACKOFF_MS = 2000;
const MAX_RATE_LIMIT_RETRIES = 5;

function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}

// BigInt-safe — plain JSON.stringify throws on any bigint field, which a
// GenLayerTransaction (u256 storage values, wei amounts) commonly has.
export function safeStringify(value: unknown): string {
  return JSON.stringify(value, (_k, v) => (typeof v === "bigint" ? v.toString() : v), 2);
}

// Viem (which genlayer-js is built on) commonly nests the real JSON-RPC
// error under `.cause`, sometimes more than one level deep — checked
// recursively rather than assuming a fixed depth, plus a message-text
// fallback since the exact wrapping shape for a Bradbury -32005 response
// specifically hasn't been confirmed against a live example.
function extractErrorCode(err: unknown, depth = 0): number | undefined {
  if (depth > 5 || !err || typeof err !== "object") return undefined;
  const e = err as Record<string, unknown>;
  if (typeof e.code === "number") return e.code;
  if ("cause" in e) return extractErrorCode(e.cause, depth + 1);
  return undefined;
}

function isRateLimitError(err: unknown): boolean {
  if (extractErrorCode(err) === RATE_LIMIT_ERROR_CODE) return true;
  const message = err instanceof Error ? err.message : String(err);
  return message.includes("-32005") || /rate limit/i.test(message);
}

export async function withRateLimitRetry<T>(label: string, fn: () => Promise<T>): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (!isRateLimitError(err) || attempt >= MAX_RATE_LIMIT_RETRIES) throw err;
      console.warn(
        `  ${label}: rate limited (-32005) — retrying in ${RATE_LIMIT_BACKOFF_MS}ms ` +
          `(attempt ${attempt + 1}/${MAX_RATE_LIMIT_RETRIES})`
      );
      await sleep(RATE_LIMIT_BACKOFF_MS);
    }
  }
}

// Checks every field observed to actually carry the status across a live
// receipt (camelCase per the .d.ts, snake_case per what the client really
// returned, and numeric as a last resort) rather than trusting any one of
// them alone — see deploy.ts header's third-round note.
function isAcceptedOrFinalized(receipt: GenLayerTransaction): boolean {
  const nameFromSnakeCase = (receipt as unknown as { status_name?: string }).status_name;
  const numericStatus = typeof receipt.status === "number" ? receipt.status : undefined;
  const acceptedNumber = Number(transactionsStatusNameToNumber[TransactionStatus.ACCEPTED]);
  const finalizedNumber = Number(transactionsStatusNameToNumber[TransactionStatus.FINALIZED]);

  return (
    receipt.statusName === TransactionStatus.ACCEPTED ||
    receipt.statusName === TransactionStatus.FINALIZED ||
    nameFromSnakeCase === TransactionStatus.ACCEPTED ||
    nameFromSnakeCase === TransactionStatus.FINALIZED ||
    numericStatus === acceptedNumber ||
    numericStatus === finalizedNumber
  );
}

function extractDeployedAddress(receipt: GenLayerTransaction, contractName: string): string {
  // Priority order, see deploy.ts's header note:
  // 1. The exact typed cast confirmed against a live deploy receipt.
  const decoded = (receipt.txDataDecoded as DecodedDeployData)?.contractAddress;
  // 2. The raw snake_case field observed directly on a live receipt —
  // not in GenLayerTransaction's declared type at all, accessed loosely.
  const raw = (receipt as unknown as { contract_address?: string }).contract_address;
  const address = decoded ?? raw ?? receipt.recipient ?? receipt.to_address;

  if (!address) {
    throw new Error(
      `${contractName}: couldn't find a deployed address on the transaction receipt ` +
        `(checked txDataDecoded.contractAddress, contract_address, recipient, and to_address — ` +
        `all empty). Full receipt: ${safeStringify(receipt)}`
    );
  }
  return address;
}

export interface DeployTarget {
  name: string;
  file: string;
  args: unknown[];
}

/** Deploys one contract (contracts/<file>) with `args`, waits for
 * ACCEPTED, and returns its address — the exact engine deploy.ts's
 * bootstrap deployments use, verified live against Bradbury multiple
 * times (see this file's header). Throws with the full receipt on any
 * failure — consensus-level (bad status) or execution-level
 * (FINISHED_WITH_ERROR, e.g. a real contract bug). */
export async function deployOne(
  client: ReturnType<typeof createClient>,
  target: DeployTarget
): Promise<string> {
  const contractPath = resolve(CONTRACTS_DIR, target.file);
  if (!existsSync(contractPath)) {
    throw new Error(`Contract source not found: ${contractPath}`);
  }
  // Raw bytes, not a UTF-8 string — see deploy.ts header's second-round note.
  const code = new Uint8Array(readFileSync(contractPath));

  const txHash = await withRateLimitRetry(`${target.name} deployContract`, () =>
    client.deployContract({
      code,
      args: target.args as never,
    })
  );

  // retries/interval set explicitly (60 * 3s = 3 minutes) — the default
  // wasn't long enough to cover a real commit/reveal round on Bradbury;
  // see deploy.ts header's second-round note.
  const receipt = await withRateLimitRetry(`${target.name} waitForTransactionReceipt`, () =>
    client.waitForTransactionReceipt({
      hash: txHash as TransactionHash,
      status: TransactionStatus.ACCEPTED,
      retries: 60,
      interval: 3000,
    })
  );

  const statusOk = isAcceptedOrFinalized(receipt);
  const executionFailed = receipt.txExecutionResultName === ExecutionResult.FINISHED_WITH_ERROR;

  if (!statusOk || executionFailed) {
    const observedStatus =
      receipt.statusName ?? (receipt as unknown as { status_name?: string }).status_name ?? receipt.status;
    throw new Error(
      `${target.name} deployment failed — status: ${observedStatus}, ` +
        `execution: ${receipt.txExecutionResultName ?? "unknown"}. ` +
        `Full receipt: ${safeStringify(receipt)}`
    );
  }

  return extractDeployedAddress(receipt, target.name);
}
