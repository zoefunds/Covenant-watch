"use client";

import { useAppKitAccount, useAppKitProvider } from "@reown/appkit/react";
import type { Signer } from "./contract";

/** The connected wallet's provider+address, ready to pass into every
 * contract write call in lib/contract.ts. Returns null when not connected
 * or not yet authenticated via SIWE (callers should gate on session too). */
export function useSigner(): Signer | null {
  const { address, isConnected } = useAppKitAccount();
  const { walletProvider } = useAppKitProvider<any>("eip155");
  if (!isConnected || !address || !walletProvider) return null;
  return { provider: walletProvider, address };
}
