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