// Contract-address env wiring — deliberately separate from lib/api.ts's
// NEXT_PUBLIC_API_URL (that one always has a working localhost fallback;
// these three don't, because there is nothing to fall back to before
// Chibuikem's deploy script runs — see ROADMAP.md 4.6's SYNC POINT).
//
// Every call site MUST handle `null` — that's the real, current state of
// this app (nothing deployed yet), not a hypothetical edge case. Treat a
// null contract address as "route this through the legacy off-chain path",
// exactly like an escrow/dispute created before the cutover.

export type ContractKind = "escrow" | "disputeCourt" | "predictionMarket";

const ENV_VAR: Record<ContractKind, string | undefined> = {
  escrow: process.env.NEXT_PUBLIC_ESCROW_CONTRACT_ADDRESS,
  disputeCourt: process.env.NEXT_PUBLIC_DISPUTE_COURT_CONTRACT_ADDRESS,
  predictionMarket: process.env.NEXT_PUBLIC_PREDICTION_MARKET_CONTRACT_ADDRESS,
};

/** The deployed address for `kind`, or null if it isn't configured yet —
 * null means "no live contract to point at," not an error. */
export function contractAddress(kind: ContractKind): `0x${string}` | null {
  const raw = ENV_VAR[kind]?.trim();
  return raw ? (raw as `0x${string}`) : null;
}

/** True once every contract this app needs is actually deployed and
 * wired up. Until then, submit flows stay on the legacy off-chain path
 * for everything, not just escrows that predate a partial cutover. */
export function isOnChainConfigured(): boolean {
  return (
    contractAddress("escrow") !== null &&
    contractAddress("disputeCourt") !== null &&
    contractAddress("predictionMarket") !== null
  );
}
