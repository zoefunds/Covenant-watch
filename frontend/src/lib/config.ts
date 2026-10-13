// Central, typed config. Every address / endpoint the app talks to lives
// here so nothing is hardcoded inline in a component.

// Contract used by the current frontend deployment.
export const CONTRACT_ADDRESS = (process.env.NEXT_PUBLIC_CONTRACT_ADDRESS ||
  "0xa49283a086fE5122Cf3967b6ADb50A50fA736905") as `0x${string}`;

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
export const BASE_USDC_ADDRESS = (process.env.NEXT_PUBLIC_BASE_USDC_ADDRESS || "0x036CbD53842c5426634e7929541eC2318f3dCF7e") as `0x${string}`;
export const BASE_ESCROW_ADDRESS = (process.env.NEXT_PUBLIC_BASE_ESCROW_ADDRESS || "0x8D9cc4Efd412cEd3c10de543a46b8390CAa8ADe7") as `0x${string}`;
export const BASE_EXPLORER_URL = "https://sepolia.basescan.org";

export const GENLAYER_EXPLORER_URL =
  process.env.NEXT_PUBLIC_GENLAYER_EXPLORER_URL || "https://explorer-studio.genlayer.com/";

// Reown (WalletConnect) AppKit project id — https://dashboard.reown.com.
// AppKit only handles wallet CONNECTION; it is never treated as
// authentication on its own — every session still goes through the real
// SIWE nonce/verify round trip against the backend (see WalletContext).
export const REOWN_PROJECT_ID = process.env.NEXT_PUBLIC_REOWN_PROJECT_ID || "";
