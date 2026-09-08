// scripts/genlayer-deploy.ts — Part 2, closing the loop: auto-deploy per
// new escrow.
//
// A thin deploy bridge invoked as a subprocess by backend/app/services/
// genlayer_deploy.py, right after a new escrow is created — deploys ONE
// fresh NuanceEscrow instance with that escrow's real counterparty/
// milestone data, using the exact same proven engine (scripts/
// genlayer-deploy-core.ts) and the exact same deployer key scripts/
// deploy.ts's bootstrap instances already use.
//
// Deliberately server-side, not wallet-signed from the browser like
// submit_deliverable/file_dispute (components/app/genlayer-write-client.ts)
// are: deploying needs the contract source's raw bytes, which a browser
// bundle has no reason to ship, and GENLAYER_PRIVATE_KEY was never meant
// to reach client-side JS. This is exactly what deploy.ts's own header
// already called out as the plan: "a new escrow between two real users
// still needs its own fresh deployment with their real data, called from
// the app itself once that wiring exists (a Step 4/backend-integration
// concern)."
//
// Protocol: one JSON object on stdin —
//   { "file": "nuance_escrow.py", "args": [...] }
// — one JSON object on stdout —
//   { "ok": true, "address": "0x..." } | { "ok": false, "error": "..." }
// A deploy can take up to ~3 minutes (deployOne's own receipt-wait) —
// this process simply runs for that long; the caller (genlayer_deploy.py)
// awaits it as a background task, never blocking a request.

import { createAccount, createClient, chains } from "genlayer-js";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { deployOne, safeStringify, REPO_ROOT } from "./genlayer-deploy-core";

const BACKEND_ENV_PATH = resolve(REPO_ROOT, "backend/.env");

function loadEnvFile(path: string): void {
  if (existsSync(path)) process.loadEnvFile(path);
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("utf-8");
}

interface DeployRequest {
  file: string;
  args: unknown[];
}

async function main() {
  loadEnvFile(BACKEND_ENV_PATH);
  const privateKey = process.env.GENLAYER_PRIVATE_KEY;
  if (!privateKey) {
    process.stdout.write(
      safeStringify({ ok: false, error: `GENLAYER_PRIVATE_KEY not set in ${BACKEND_ENV_PATH}.` })
    );
    return;
  }

  const raw = await readStdin();
  // Reviver for backend/app/services/genlayer_deploy.py's `_bigint_arg`
  // shape ({"__bigint__": "<digits>"}) — converts it back into a real
  // BigInt *before* it ever becomes a JS `number`. Plain JSON.parse turns
  // any numeric literal into a double, exact only up to 2**53; a wei-scale
  // u256 constructor arg (GEN's 18 decimals push this past 10**18) would
  // silently lose precision that way. See _bigint_arg's own docstring for
  // the full reasoning — genlayer-js's calldata encoder only preserves
  // full precision for its `case "bigint"` branch (encodeImpl in
  // node_modules/genlayer-js/dist/index.js), not `case "number"`.
  const request = JSON.parse(raw, (_key, value) => {
    if (value && typeof value === "object" && "__bigint__" in value) {
      return BigInt((value as { __bigint__: string }).__bigint__);
    }
    return value;
  }) as DeployRequest;

  const account = createAccount(privateKey as `0x${string}`);
  const client = createClient({ chain: chains.testnetBradbury, account });

  try {
    const address = await deployOne(client, {
      name: request.file,
      file: request.file,
      args: request.args ?? [],
    });
    process.stdout.write(safeStringify({ ok: true, address }));
  } catch (err) {
    // Same principle as scripts/genlayer-read.ts: a failed deploy is a
    // per-item ok:false in a normally-exiting JSON body, not a thrown
    // process failure — the Python caller treats this as "stay off-chain,"
    // not a crash. Only a malformed request (bad JSON on stdin, e.g.)
    // reaches the outer .catch below and exits non-zero.
    process.stdout.write(safeStringify({ ok: false, error: errorMessage(err) }));
  }
}

main().catch((err) => {
  process.stderr.write(`genlayer-deploy fatal: ${errorMessage(err)}\n`);
  process.exitCode = 1;
});
