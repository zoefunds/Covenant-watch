"use client";

import { createPublicClient, encodeFunctionData, http, parseUnits } from "viem";
import { baseSepolia } from "viem/chains";
import type { Signer } from "./contract";
import { BASE_ESCROW_ADDRESS, BASE_USDC_ADDRESS } from "./config";

const escrowAbi = [
  { type: "function", name: "loanCount", stateMutability: "view", inputs: [], outputs: [{ type: "uint256" }] },
  { type: "function", name: "createLoan", stateMutability: "nonpayable", inputs: [
    { name: "borrower", type: "address" }, { name: "principal", type: "uint256" },
    { name: "collateral", type: "uint256" }, { name: "interestBps", type: "uint32" },
    { name: "maturity", type: "uint64" }], outputs: [{ name: "loanId", type: "uint256" }] },
  { type: "function", name: "stakeCollateral", stateMutability: "nonpayable", inputs: [{ name: "loanId", type: "uint256" }], outputs: [] },
  { type: "function", name: "claimPrincipal", stateMutability: "nonpayable", inputs: [{ name: "loanId", type: "uint256" }], outputs: [] },
  { type: "function", name: "repay", stateMutability: "nonpayable", inputs: [{ name: "loanId", type: "uint256" }], outputs: [] },
  { type: "function", name: "claimSettlement", stateMutability: "nonpayable", inputs: [{ name: "loanId", type: "uint256" }], outputs: [] },
] as const;
const erc20Abi = [{ type: "function", name: "approve", stateMutability: "nonpayable", inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }], outputs: [{ type: "bool" }] }] as const;

async function ensureBase(provider: any) {
  const chain = await provider.request({ method: "eth_chainId" });
  if (String(chain).toLowerCase() === "0x14a34") return;
  try { await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: "0x14a34" }] }); }
  catch {
    await provider.request({ method: "wallet_addEthereumChain", params: [{ chainId: "0x14a34", chainName: "Base Sepolia", nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 }, rpcUrls: ["https://sepolia.base.org"], blockExplorerUrls: ["https://sepolia.basescan.org"] }] });
  }
}

async function send(signer: Signer, to: `0x${string}`, data: `0x${string}`) {
  await ensureBase(signer.provider);
  const hash = await signer.provider.request({ method: "eth_sendTransaction", params: [{ from: signer.address, to, data }] }) as `0x${string}`;
  const client = createPublicClient({ chain: baseSepolia, transport: http() });
  await client.waitForTransactionReceipt({ hash, confirmations: 1 });
  return hash;
}

export async function createBaseLoan(signer: Signer, borrower: string, principalUsdc: string, collateralUsdc: string, interestBps: number, maturity: number) {
  const client = createPublicClient({ chain: baseSepolia, transport: http() });
  const loanId = await client.readContract({ address: BASE_ESCROW_ADDRESS, abi: escrowAbi, functionName: "loanCount" });
  const principal = parseUnits(principalUsdc, 6);
  await send(signer, BASE_USDC_ADDRESS, encodeFunctionData({ abi: erc20Abi, functionName: "approve", args: [BASE_ESCROW_ADDRESS, principal] }));
  const hash = await send(signer, BASE_ESCROW_ADDRESS, encodeFunctionData({ abi: escrowAbi, functionName: "createLoan", args: [borrower as `0x${string}`, principal, parseUnits(collateralUsdc, 6), interestBps, BigInt(maturity)] }));
  return { loanId: Number(loanId), hash };
}

export async function stakeBaseCollateral(signer: Signer, loanId: number, collateralUsdc: string) {
  const amount = parseUnits(collateralUsdc, 6);
  await send(signer, BASE_USDC_ADDRESS, encodeFunctionData({ abi: erc20Abi, functionName: "approve", args: [BASE_ESCROW_ADDRESS, amount] }));
  return send(signer, BASE_ESCROW_ADDRESS, encodeFunctionData({ abi: escrowAbi, functionName: "stakeCollateral", args: [BigInt(loanId)] }));
}

export const claimBasePrincipal = (signer: Signer, loanId: number) => send(signer, BASE_ESCROW_ADDRESS, encodeFunctionData({ abi: escrowAbi, functionName: "claimPrincipal", args: [BigInt(loanId)] }));
export const claimBaseSettlement = (signer: Signer, loanId: number) => send(signer, BASE_ESCROW_ADDRESS, encodeFunctionData({ abi: escrowAbi, functionName: "claimSettlement", args: [BigInt(loanId)] }));
export async function repayBaseLoan(signer: Signer, loanId: number, dueUsdcBaseUnits: bigint) {
  await send(signer, BASE_USDC_ADDRESS, encodeFunctionData({ abi: erc20Abi, functionName: "approve", args: [BASE_ESCROW_ADDRESS, dueUsdcBaseUnits] }));
  return send(signer, BASE_ESCROW_ADDRESS, encodeFunctionData({ abi: escrowAbi, functionName: "repay", args: [BigInt(loanId)] }));
}
