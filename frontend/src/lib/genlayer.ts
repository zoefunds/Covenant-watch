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
 *
 * `account` MUST be bound here, at client-construction time, as the plain
 * address string — genlayer-js hands that straight to viem's
 * createWalletClient({ account }), which normalizes a raw address into a
 * proper Account (adding .address/.signTransaction etc.) via its own
 * parseAccount. Passing a raw address string into a per-call `account`
 * argument on writeContract/readContract instead (as this code used to)
 * skips that normalization — genlayer-js's own writeContract does
 * `senderAccount = account || client.account` and then reads
 * `senderAccount.address` directly, so a bare string there yields
 * `undefined` and fails address validation deep inside viem. Binding the
 * account on the client avoids ever taking that path.
 */
export function getWalletClient(provider: any, address?: string): GenLayerClient<any> {
  if (!provider) {
    throw new Error("No wallet connected. Use the Connect Wallet button (Reown AppKit) to continue.");
  }
  const chain = resolveChain();
  return createClient({ chain, provider, ...(address ? { account: address as `0x${string}` } : {}) });
}

async function currentChain(provider: any) {
  return String(await provider.request({ method: "eth_chainId" })).toLowerCase();
}

/** Switches the connected wallet to the configured GenLayer network and
 * verifies the result. Some wallets silently ignore the first switch request,
 * so this deliberately follows the proven Meme Olympics retry/add pattern. */
export async function ensureGenLayerNetwork(provider: any): Promise<void> {
  const chain = resolveChain();
  const chainId = `0x${Number(chain.id).toString(16)}`.toLowerCase();
  if ((await currentChain(provider)) === chainId) return;
  try {
    await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId }] });
  } catch {
    // Verify the wallet state below, independent of vendor-specific errors.
  }
  if ((await currentChain(provider)) === chainId) return;
  await provider.request({
    method: "wallet_addEthereumChain",
    params: [{
      chainId,
      chainName: chain.name,
      nativeCurrency: chain.nativeCurrency,
      rpcUrls: chain.rpcUrls.default.http,
      blockExplorerUrls: chain.blockExplorers?.default ? [chain.blockExplorers.default.url] : undefined,
    }],
  });
  await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId }] });
  if ((await currentChain(provider)) !== chainId) {
    throw new Error(`Please switch your wallet to ${chain.name} to continue.`);
  }
}

export { CONTRACT_ADDRESS };
