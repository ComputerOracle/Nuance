import type { ComponentType } from "react";
import {
  CoinbaseIcon,
  MetaMaskIcon,
  OkxIcon,
  PhantomIcon,
  RabbyIcon,
  TrustWalletIcon,
} from "@/components/app/wallet-icons";

export interface WalletCatalogEntry {
  name: string;
  rdns: string;
  installUrl: string;
  Icon: ComponentType;
}

// rdns matches the EIP-6963 identifier each wallet announces with
// (see use-wallet-detection.ts). installUrl is where "Install" sends a
// visitor who doesn't have it yet.
export const WALLET_CATALOG: WalletCatalogEntry[] = [
  {
    name: "MetaMask",
    rdns: "io.metamask",
    installUrl: "https://metamask.io/download/",
    Icon: MetaMaskIcon,
  },
  {
    name: "Phantom",
    rdns: "app.phantom",
    installUrl: "https://phantom.app/download",
    Icon: PhantomIcon,
  },
  {
    name: "Trust Wallet",
    rdns: "com.trustwallet.app",
    installUrl: "https://trustwallet.com/download",
    Icon: TrustWalletIcon,
  },
  {
    name: "Rabby Wallet",
    rdns: "io.rabby",
    installUrl: "https://rabby.io",
    Icon: RabbyIcon,
  },
  {
    name: "OKX Wallet",
    rdns: "com.okex.wallet",
    installUrl: "https://www.okx.com/web3",
    Icon: OkxIcon,
  },
  {
    name: "Coinbase Wallet",
    rdns: "com.coinbase.wallet",
    installUrl: "https://www.coinbase.com/wallet/downloads",
    Icon: CoinbaseIcon,
  },
];
