"use client";

// Reown (WalletConnect) AppKit setup — the real wallet-connect UI/flow for
// this app. AppKit only establishes a wallet connection + EIP-1193
// provider; it is NOT authentication. Every connection is still followed
// by the real SIWE nonce/verify round trip against the backend (see
// WalletContext.tsx) before the session is considered signed in.

import { createAppKit } from "@reown/appkit/react";
import { WagmiAdapter } from "@reown/appkit-adapter-wagmi";
import { defineChain } from "@reown/appkit/networks";
import { chains as genlayerChains } from "genlayer-js";
import { REOWN_PROJECT_ID, GENLAYER_NETWORK } from "./config";

const studio = (genlayerChains as Record<string, any>)[GENLAYER_NETWORK];

// Build a real AppKit/CaipNetwork definition from the exact chain genlayer-js
// itself uses for this network (id, rpc, native currency) — never invented.
export const genlayerCaipNetwork = defineChain({
  id: studio.id,
  caipNetworkId: `eip155:${studio.id}`,
  chainNamespace: "eip155",
  name: studio.name,
  nativeCurrency: studio.nativeCurrency,
  rpcUrls: studio.rpcUrls,
  blockExplorers: studio.blockExplorers,
  testnet: true,
});

export const wagmiAdapter = new WagmiAdapter({
  projectId: REOWN_PROJECT_ID,
  networks: [genlayerCaipNetwork],
});

// AppKit's own hooks (useAppKit/useAppKitAccount/...) require createAppKit
// to have run before the first render that calls them. Doing this at
// module scope (client-only — this whole file is "use client" and only
// ever imported by client components) rather than inside a useEffect
// avoids a render-order race during hydration.
let appKitInitialized = false;

export function ensureAppKit() {
  if (appKitInitialized || typeof window === "undefined") return;
  if (!REOWN_PROJECT_ID) {
    console.warn("NEXT_PUBLIC_REOWN_PROJECT_ID is not set — wallet connect UI will not initialize.");
    return;
  }
  createAppKit({
    adapters: [wagmiAdapter],
    networks: [genlayerCaipNetwork],
    projectId: REOWN_PROJECT_ID,
    metadata: {
      name: "Covenant Watch",
      description: "On-chain covenant monitoring and automatic-penalty lending on GenLayer.",
      url: typeof window !== "undefined" ? window.location.origin : "https://covenant-watch.vercel.app",
      icons: ["/icon.svg"],
    },
    features: { analytics: false, email: false, socials: [] },
  });
  appKitInitialized = true;
}

if (typeof window !== "undefined") {
  ensureAppKit();
}
