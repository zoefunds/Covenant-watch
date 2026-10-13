"use client";

import type { Signer } from "./contract";
import { useWallet } from "@/context/WalletContext";
import { getSelectedWalletProvider } from "./walletProviders";

/** The connected wallet's provider+address, ready to pass into every
 * contract write call in lib/contract.ts. Returns null when not connected
 * or not yet authenticated via SIWE (callers should gate on session too). */
export function useSigner(): Signer | null {
  const { address } = useWallet();
  const provider = getSelectedWalletProvider();
  if (!address || !provider) return null;
  return { provider, address };
}
