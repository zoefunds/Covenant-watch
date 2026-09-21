"use client";

import { createClient, chains } from "genlayer-js";
import type { GenLayerClient } from "genlayer-js/types";
import { CONTRACT_ADDRESS, GENLAYER_NETWORK } from "./config";

function resolveChain() {
  const chain = (chains as Record<string, any>)[GENLAYER_NETWORK];
  if (!chain) {
    throw new Error(`Unknown GenLayer network "${GENLAYER_NETWORK}" — check NEXT_PUBLIC_GENLAYER_NETWORK`);
  }
  return chain;
}

/**
 * Read-only client using the chain's default public RPC. No signing
 * capability required for @gl.public.view calls, so it never depends on a
 * connected wallet.
 */
export function getReadClient(): GenLayerClient<any> {
  const chain = resolveChain();
  return createClient({ chain });
}

/**
 * Write-capable client bound to whatever EIP-1193 provider Reown AppKit
 * connected (see useAppKitProvider in WalletContext) — a real wallet
 * signature request, never a simulated/local-only signer. Callers must
 * pass the live provider from the AppKit hook; there is no window.ethereum
 * fallback because AppKit is the single connect path for this app.
 */
export function getWalletClient(provider: any): GenLayerClient<any> {
  if (!provider) {
    throw new Error("No wallet connected. Use the Connect Wallet button (Reown AppKit) to continue.");
  }
  const chain = resolveChain();
  return createClient({ chain, provider });
}

export { CONTRACT_ADDRESS };
