// Central, typed config. Every address / endpoint the app talks to lives
// here so nothing is hardcoded inline in a component.

// Contract used by the current frontend deployment.
export const CONTRACT_ADDRESS = (process.env.NEXT_PUBLIC_CONTRACT_ADDRESS ||
  "0x5aD6959559D0eF030a62C625b9071eBE655af74a") as `0x${string}`;

// "studionet" is the network this project's contract is actually deployed
// on (see memory.md). Kept configurable so a user who redeploys elsewhere
// (localnet / testnetAsimov / testnetBradbury) only needs an env change.
export const GENLAYER_NETWORK = (process.env.NEXT_PUBLIC_GENLAYER_NETWORK || "studionet") as
  | "localnet"
  | "studionet"
  | "testnetAsimov"
  | "testnetBradbury"
  | "mainnet";

export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "https://covenant-watch-api.fly.dev";

export const GENLAYER_EXPLORER_URL =
  process.env.NEXT_PUBLIC_GENLAYER_EXPLORER_URL || "https://explorer-studio.genlayer.com/";

// Reown (WalletConnect) AppKit project id — https://dashboard.reown.com.
// AppKit only handles wallet CONNECTION; it is never treated as
// authentication on its own — every session still goes through the real
// SIWE nonce/verify round trip against the backend (see WalletContext).
export const REOWN_PROJECT_ID = process.env.NEXT_PUBLIC_REOWN_PROJECT_ID || "";
