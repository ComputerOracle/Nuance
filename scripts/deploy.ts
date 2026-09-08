// scripts/deploy.ts — Part 2, Step 3.
//
// Deploys NuanceEscrow, NuanceDisputeCourt, and NuancePredictionMarket to
// GenLayer's Bradbury testnet, waits for each transaction to reach
// ACCEPTED, and writes the resulting addresses into backend/.env and
// .env.local.
//
// Run with:  npm run deploy:contracts
//
// --- Sources & confidence ---
// Every genlayer-js call below (createAccount, createClient, chains.
// testnetBradbury, client.deployContract, client.waitForTransactionReceipt,
// TransactionStatus.ACCEPTED/.FINALIZED, GenLayerTransaction's fields) is
// read directly from the actually-installed package's own .d.ts files
// (node_modules/genlayer-js@1.1.8/dist/index.d.ts and index-C3Ul1Rte.d.ts)
// and its compiled chains/index.cjs — the same verification method Emma's
// lib/chain-status.ts already established for this package, not the docs
// site. Confirmed at runtime: testnetBradbury.id === 4221, rpcUrls ===
// ["https://rpc-bradbury.genlayer.com"], matching this step's brief and
// ROADMAP.md 4.6 exactly.
//
// Address extraction (updated 2026-09-06, after the first real Bradbury
// attempt came back "ACCEPTED (ERROR)"): the properly-typed field is
// `txDataDecoded.contractAddress` on DecodedDeployData (confirmed in
// node_modules/genlayer-js/dist/index-C3Ul1Rte.d.ts:146) — camelCase,
// nested, only populated for a decoded deploy transaction. That's
// distinct from the raw snake_case `contract_address` observed directly
// on a live receipt, which the strict GenLayerTransaction type doesn't
// declare at all (pre-mainnet SDKs commonly lag the real wire shape).
// extractDeployedAddress() checks both, plus the original recipient/
// to_address guesses as a last resort, and fails loudly with the full
// (BigInt-safe) receipt rather than silently writing a wrong address if
// none of them are present.
//
// Rate limiting: Bradbury has returned JSON-RPC error -32005 under load.
// withRateLimitRetry() wraps each individual RPC call (deployContract,
// waitForTransactionReceipt) — never the whole deployOne() — specifically
// so a rate-limit hit during the *receipt* wait can't cause a duplicate
// deployment transaction by retrying deployContract again.
//
// Second round of corrections (2026-09-06, after the fixed Depends hash
// got a real deployment to Decided: Accepted but the client then timed
// out waiting for the receipt while the tx sat at status 4/REVEALING):
//   - Contract code is now passed as raw bytes (new Uint8Array over the
//     file's Buffer) rather than a UTF-8 string — deployContract accepts
//     `string | Uint8Array` per its own type; bytes avoid any encoding
//     step string-mode might apply.
//   - waitForTransactionReceipt's retries/interval are now set explicitly
//     (60 attempts * 3s = 3 minutes) instead of relying on its default,
//     which wasn't long enough to cover a real commit/reveal round
//     actually playing out on Bradbury.
//   - extractDeployedAddress leads with the exact typed cast
//     `(receipt.txDataDecoded as DecodedDeployData)?.contractAddress`,
//     keeping the other fields only as fallbacks.
//
// Third round (same day, after the above got a real ACCEPTED receipt with
// a real contractAddress back, and this script still threw "got
// undefined"): `receipt.statusName` — the camelCase field the installed
// .d.ts declares — was never actually populated on the live response;
// the real object had `status: 5` and a snake_case `status_name:
// "ACCEPTED"` instead. isAcceptedOrFinalized() below checks the raw
// snake_case field and a numeric comparison (via the SDK's own
// transactionsStatusNameToNumber lookup, not a hardcoded 5) alongside the
// typed camelCase field, so whichever one the client actually populates
// works. Separately — and this is the fix that actually mattered for
// TreeMap[K, V]() being wrong in the contracts themselves — reaching
// ACCEPTED is a consensus-layer result, not proof the contract's own code
// ran successfully: a transaction can be ACCEPTED while
// txExecutionResultName is FINISHED_WITH_ERROR, which is exactly what a
// GenericAlias-not-callable TypeError inside __init__ produced. Both are
// now checked.
//
// Fourth round (same day, NuancePredictionMarket only — the other two
// contracts were already live by this point): ACCEPTED with
// FINISHED_WITH_ERROR again, but a genuinely new cause this time, found
// via `client.debugTraceTransaction({hash})` (its stderr carries the real
// Python traceback; the transaction receipt alone does not) —
// `self.claimed = TreeMap()` failed
// `AssertionError: Is right the same storage type? TreeMap <- TreeMap`
// in genlayer/py/storage/_internal/desc_record.py, while the two
// TreeMap[Address, u256] fields assigned immediately before it in the
// same __init__ succeeded. Isolated to `bool` as a TreeMap's value type
// specifically — worked around in nuance_prediction_market.py by storing
// 0/1 (u256) instead of True/False; see that file's own header comment on
// the `claimed` field for the full account. All three contracts deployed
// successfully after this fix — see ROADMAP.md Part 2 / 4.4 for the live
// addresses.
//
// Fifth round (2026-09-06, NuanceGovernance — added after the other three
// were already live, on direct request; not part of the original Part 2
// plan): the bool-TreeMap finding above turned out to be one instance of
// a broader rule, not the whole story. Two more failed deploy attempts
// (both ACCEPTED/FINISHED_WITH_ERROR, both re-diagnosed via
// debugTraceTransaction) hit the identical assertion on a SECOND TreeMap
// field with a different (K, V) shape than the contract's first — first a
// bare TreeMap[u256, u256], then even TreeMap[u256, VoteRecord] (a second
// *dataclass* value type, structurally as close to the first TreeMap as
// possible). The actual rule: a contract may only have ONE distinct
// TreeMap[K, V] shape, full stop — every TreeMap field must share the
// exact same type parameterization, not just avoid bool. Fixed in
// nuance_governance.py by collapsing to a single TreeMap[u256, Record],
// with one polymorphic dataclass covering both proposals and vote
// records (see that file's header for the full account and the field-
// reuse scheme). Verified live afterward with a real create_proposal ->
// cast_vote -> re-vote -> finalize_proposal sequence against the
// deployed contract, not just a clean deploy — confirmed the re-vote
// flip-not-stack logic and the quorum/pass-threshold math both work
// against actual chain state.
//
// --- What this script is, and isn't ---
// Deploying NuanceEscrow / NuancePredictionMarket here creates ONE
// concrete instance with real constructor args baked in immediately (that
// is how GenVM deployment works — there's no separate "factory" step).
// That's the correct, permanent, production pattern for NuanceDisputeCourt
// (a genuine shared registry — see that contract's own header). For
// Escrow and Prediction Market it is NOT the real per-agreement flow going
// forward: a new escrow between two real users still needs its own fresh
// deployment with their real data, called from the app itself once that
// wiring exists (a Step 4/backend-integration concern). This script's
// Escrow/Prediction Market deployments are a bootstrap: proving the
// contracts actually deploy on Bradbury and giving Emma's frontend one
// real, live address to build lib/chain-config.ts's cutover against.

import { createAccount, createClient, chains } from "genlayer-js";
import { writeFileSync, existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { deployOne, REPO_ROOT } from "./genlayer-deploy-core";

// 2026-09-07: the deploy engine itself (deployOne, extractDeployedAddress,
// isAcceptedOrFinalized, rate-limit retry — everything the "Second/Third/
// Fourth round" notes below describe) moved to scripts/genlayer-deploy-core.ts
// so scripts/genlayer-deploy.ts (the per-escrow auto-deploy bridge
// backend/app/services/genlayer_deploy.py invokes) can reuse it rather
// than duplicate five rounds of hard-won live-Bradbury fixes. Behavior
// here is unchanged — this file is now the CLI orchestration
// (which contracts, what args, writing addresses into both .env files)
// around that shared engine.

const BACKEND_ENV_PATH = resolve(REPO_ROOT, "backend/.env");
const FRONTEND_ENV_PATH = resolve(REPO_ROOT, ".env.local");
// Step 3's brief says "frontend/.env.local" — this repo's Next.js app is
// the repo root itself (no frontend/ subdirectory exists; see
// .env.local.example living at the root), so that's where the real file
// actually needs to be for Next.js to pick it up.

// Deploying three contracts back-to-back is exactly the kind of burst
// that trips -32005 in the first place — space them out regardless of
// whether any single call got rate-limited.
const DELAY_BETWEEN_DEPLOYMENTS_MS = 5000;

function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}

// --- Demo constructor args for the bootstrap Escrow/Prediction Market
// deployments (see header) — override via env if you want different
// values without editing this file.
const DEMO_COUNTERPARTY =
  process.env.DEPLOY_DEMO_COUNTERPARTY_ADDRESS ??
  "0x1111111111111111111111111111111111111111";

interface ContractSpec {
  name: string;
  file: string;
  // Positional constructor args, in the exact order each contract's
  // __init__ declares them.
  args: unknown[];
  // Key names to write once deployed.
  backendEnvKey: string;
  frontendEnvKey: string;
}

async function main() {
  loadEnvFile(BACKEND_ENV_PATH);

  const privateKey = process.env.GENLAYER_PRIVATE_KEY;
  if (!privateKey) {
    throw new Error(
      `GENLAYER_PRIVATE_KEY not found in ${BACKEND_ENV_PATH} — set it before running this script.`
    );
  }

  const account = createAccount(privateKey as `0x${string}`);
  const client = createClient({
    chain: chains.testnetBradbury,
    account,
  });

  console.log(`Deployer address: ${account.address}`);
  console.log(`Chain: ${chains.testnetBradbury.name} (id ${chains.testnetBradbury.id})`);
  console.log(`RPC:   ${chains.testnetBradbury.rpcUrls.default.http[0]}\n`);

  // All four are live on Bradbury as of 2026-09-06 (this run's own
  // output — see ROADMAP.md 4.4 for the addresses). Re-running this script
  // from here deploys six BRAND NEW instances and overwrites the env
  // vars to point at them — correct for a from-scratch environment, but
  // it orphans the current live addresses if anything still depends on
  // them. Comment out entries you want to keep as-is before re-running
  // against an environment that already has some of these deployed.
  // All six are live on Bradbury as of 2026-09-06 (this run's own
  // output — see ROADMAP.md 4.4 for the addresses). Re-running this
  // script from here deploys six BRAND NEW instances and overwrites the
  // env vars to point at them — correct for a from-scratch environment,
  // but it orphans the current live addresses if anything still depends
  // on them. Comment out entries you want to keep as-is before
  // re-running against an environment that already has some deployed.
  const specs: ContractSpec[] = [
    {
      name: "NuanceDisputeCourt",
      file: "nuance_dispute_court.py",
      args: [], // no constructor args — see that contract's __init__
      backendEnvKey: "DISPUTE_COURT_CONTRACT_ADDRESS",
      frontendEnvKey: "NEXT_PUBLIC_DISPUTE_COURT_CONTRACT_ADDRESS",
    },
    {
      name: "NuanceEscrow",
      file: "nuance_escrow.py",
      args: [
        DEMO_COUNTERPARTY,
        "Bootstrap milestone",
        BigInt(1), // milestone_amount: u256 — 1 wei-equivalent unit, this is a
        // proof-of-deployment instance, not a real agreement (see header)
        "Deployment smoke-test placeholder — not a real milestone.",
      ],
      backendEnvKey: "ESCROW_CONTRACT_ADDRESS",
      frontendEnvKey: "NEXT_PUBLIC_ESCROW_CONTRACT_ADDRESS",
    },
    {
      name: "NuancePredictionMarket",
      file: "nuance_prediction_market.py",
      args: [
        "Bootstrap deployment smoke-test — will this contract deploy on Bradbury?",
        "https://docs.genlayer.com/",
        "Resolves YES once this deployment is confirmed on-chain.",
        "n/a — placeholder instance, see script header",
      ],
      backendEnvKey: "PREDICTION_MARKET_CONTRACT_ADDRESS",
      frontendEnvKey: "NEXT_PUBLIC_PREDICTION_MARKET_CONTRACT_ADDRESS",
    },
    {
      name: "NuanceGovernance",
      file: "nuance_governance.py",
      args: [], // no constructor args — a shared registry, like NuanceDisputeCourt
      backendEnvKey: "GOVERNANCE_CONTRACT_ADDRESS",
      frontendEnvKey: "NEXT_PUBLIC_GOVERNANCE_CONTRACT_ADDRESS",
    },
    {
      name: "NuanceValidators",
      file: "nuance_validators.py",
      args: [], // no constructor args — seeds its own 3 known validator ids internally
      backendEnvKey: "VALIDATORS_CONTRACT_ADDRESS",
      frontendEnvKey: "NEXT_PUBLIC_VALIDATORS_CONTRACT_ADDRESS",
    },
    {
      name: "NuanceAgentDirectory",
      file: "nuance_agent_directory.py",
      args: [], // no constructor args — a shared registry, like NuanceDisputeCourt
      backendEnvKey: "AGENT_DIRECTORY_CONTRACT_ADDRESS",
      frontendEnvKey: "NEXT_PUBLIC_AGENT_DIRECTORY_CONTRACT_ADDRESS",
    },
  ];

  const deployed: Record<string, string> = {};

  for (let i = 0; i < specs.length; i++) {
    const spec = specs[i];
    console.log(`--- Deploying ${spec.name} ---`);
    const address = await deployOne(client, spec);
    deployed[spec.backendEnvKey] = address;
    console.log(`${spec.name} deployed at ${address}\n`);

    upsertEnvVar(BACKEND_ENV_PATH, spec.backendEnvKey, address);
    upsertEnvVar(FRONTEND_ENV_PATH, spec.frontendEnvKey, address);

    if (i < specs.length - 1) {
      console.log(`  (waiting ${DELAY_BETWEEN_DEPLOYMENTS_MS}ms before the next deployment)\n`);
      await sleep(DELAY_BETWEEN_DEPLOYMENTS_MS);
    }
  }

  console.log("All contracts deployed and addresses written:");
  for (const spec of specs) {
    console.log(`  ${spec.backendEnvKey} / ${spec.frontendEnvKey} = ${deployed[spec.backendEnvKey]}`);
  }
  console.log(`\nWritten to:\n  ${BACKEND_ENV_PATH}\n  ${FRONTEND_ENV_PATH}`);
}

function loadEnvFile(path: string): void {
  if (!existsSync(path)) return;
  // Node 20.6+ built-in — no dotenv dependency needed.
  process.loadEnvFile(path);
}

function upsertEnvVar(path: string, key: string, value: string): void {
  const line = `${key}=${value}`;
  if (!existsSync(path)) {
    writeFileEnsuringDir(path, line + "\n");
    return;
  }
  const content = readFileSync(path, "utf-8");
  const pattern = new RegExp(`^${key}=.*$`, "m");
  const next = pattern.test(content)
    ? content.replace(pattern, line)
    : content.replace(/\n?$/, "\n") + line + "\n";
  writeFileEnsuringDir(path, next);
}

function writeFileEnsuringDir(path: string, content: string): void {
  // Both target files (backend/.env, .env.local) already have parent
  // directories that exist in this repo, so no mkdir handling needed —
  // kept as a single named function for a clear place to add it if this
  // script is ever pointed somewhere else.
  writeFileSync(path, content);
}

main().catch((err) => {
  console.error("Deployment failed:", err);
  process.exitCode = 1;
});
