// GenLayer Testnet Bradbury network parameters — pulled from the official
// SDK (github.com/genlayerlabs/genlayer-js, src/chains/testnetBradbury.ts),
// not guessed. Used to detect/prompt a network switch after connecting a
// wallet, matching the landing page's "Built on GenLayer · Testnet
// Bradbury" claim with an actual working connection instead of a mock one.
export const GENLAYER_BRADBURY = {
  chainIdHex: "0x107d",
  chainIdDecimal: 4221,
  chainName: "Genlayer Bradbury Testnet",
  rpcUrl: "https://rpc-bradbury.genlayer.com",
  nativeCurrency: { name: "GEN Token", symbol: "GEN", decimals: 18 },
  blockExplorerUrl: "https://explorer-bradbury.genlayer.com/",
} as const;

// The exact shape EIP-3085 `wallet_addEthereumChain` expects.
export const GENLAYER_BRADBURY_ADD_CHAIN_PARAMS = {
  chainId: GENLAYER_BRADBURY.chainIdHex,
  chainName: GENLAYER_BRADBURY.chainName,
  nativeCurrency: GENLAYER_BRADBURY.nativeCurrency,
  rpcUrls: [GENLAYER_BRADBURY.rpcUrl],
  blockExplorerUrls: [GENLAYER_BRADBURY.blockExplorerUrl],
};

// --- GEN <-> wei conversion --------------------------------------------
//
// GEN has 18 decimals, same as ETH (confirmed above, from the official
// SDK's own chain params) — a real payable call's `value` has to be in
// wei, not the human "2.5 GEN" figure this app shows. Every conversion
// below is done with plain BigInt integer math (string-split, then one
// multiplication), never a floating-point `* 10**18`, which would risk
// silent precision drift on the exact amounts real money is moving in —
// same principle use-wallet-connection.ts's formatNativeBalance already
// follows for the reverse (wei -> display) direction.

const WEI_PER_GEN = BigInt("1000000000000000000"); // 10^18
// 1 milli-GEN (the unit bet amounts are stored/sent in — see
// backend/app/schemas/core.py's BET_AMOUNTS_MILLI_GEN) = 10^-3 GEN =
// 10^15 wei. An exact integer multiplication, since milli-GEN amounts are
// already whole numbers — no string-parsing needed for this specific
// conversion, unlike the general decimal case below.
const WEI_PER_MILLI_GEN = BigInt("1000000000000000"); // 10^15

/** Converts a whole milli-GEN amount (500 = 0.5 GEN, matching the bet
 * quick-pick presets) to wei, for betOnChain's payable `value`. */
export function milliGenToWei(milliGen: number): bigint {
  return BigInt(milliGen) * WEI_PER_MILLI_GEN;
}

/** Converts an arbitrary decimal GEN amount (a number, or a string like
 * the backend's own Decimal-serialized "2.50") to wei, for
 * fundEscrowOnChain's payable `value`. String-split-then-BigInt rather
 * than `Number(amount) * 10**18` — floating-point multiplication can't
 * represent 10^18 exactly for every decimal input, and this is real GEN
 * leaving a wallet, not a cosmetic display number. Truncates (doesn't
 * round) anything past 18 decimal places, same convention real
 * parseUnits-style helpers use. */
export function parseGenToWei(amount: number | string): bigint {
  const str = typeof amount === "number" ? amount.toString() : amount.trim();
  const negative = str.startsWith("-");
  const unsigned = negative ? str.slice(1) : str;
  const [wholePart, fracPart = ""] = unsigned.split(".");
  const paddedFrac = (fracPart + "0".repeat(GENLAYER_BRADBURY.nativeCurrency.decimals)).slice(
    0,
    GENLAYER_BRADBURY.nativeCurrency.decimals
  );
  const combined = `${wholePart || "0"}${paddedFrac}`;
  const value = BigInt(combined === "" ? "0" : combined);
  return negative ? -value : value;
}

// Kept for anywhere that needs the raw constant rather than calling
// parseGenToWei(1) — e.g. a future display-side "X wei = Y GEN" helper.
export { WEI_PER_GEN };