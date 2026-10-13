"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authMe, authNonce, authVerify, authLogout } from "@/lib/api";
import { clearSelectedWalletProvider, requestWalletProvider } from "@/lib/walletProviders";

interface WalletState {
  address: string | null;
  sessionAddress: string | null; // address the backend session actually authenticated via SIWE
  connecting: boolean;
  authenticating: boolean;
  error: string | null;
  openConnectModal: () => void;
  signInWithEthereum: () => Promise<void>;
  disconnect: () => Promise<void>;
}

const WalletContext = createContext<WalletState | null>(null);

export function WalletProvider({ children }: { children: React.ReactNode }) {
  const [address, setAddress] = useState<string | null>(null);
  const [sessionAddress, setSessionAddress] = useState<string | null>(null);
  const [authenticating, setAuthenticating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  // Restore an existing backend session (httpOnly cookie) on load.
  useEffect(() => {
    authMe()
      .then((s) => setSessionAddress(s.address))
      .catch(() => setSessionAddress(null));
  }, []);

  // If the wallet disconnects or switches account, the old backend session
  // no longer represents "the connected wallet" — derive that locally
  // (rather than setState-in-effect) so the UI never shows a stale
  // authenticated state. The httpOnly cookie itself is only cleared via
  // /auth/logout on explicit sign-out.
  const sessionMatchesWallet = sessionAddress && address ? sessionAddress.toLowerCase() === address.toLowerCase() : false;
  const effectiveSessionAddress = sessionMatchesWallet ? sessionAddress : null;

  const openConnectModal = useCallback(async () => {
    setError(null);
    setConnecting(true);
    try {
      const provider = await requestWalletProvider();
      const accounts = await provider.request({ method: "eth_requestAccounts" }) as string[];
      if (!accounts?.[0]) throw new Error("No account returned by wallet.");
      setAddress(accounts[0]);
      provider.on?.("accountsChanged", (...args: any[]) => {
        setAddress(((args[0] as string[])?.[0]) || null);
      });
    } catch (err: any) {
      setError(err?.message || "Wallet connection failed");
    } finally {
      setConnecting(false);
    }
  }, []);

  // Real SIWE-style round trip: nonce -> personal_sign through the exact
  // EIP-6963 provider selected above -> backend verification.
  const signInWithEthereum = useCallback(async () => {
    if (!address) {
      setError("Connect a wallet first.");
      return;
    }
    setError(null);
    setAuthenticating(true);
    try {
      const provider = await requestWalletProvider();
      const nonceRes = await authNonce(address);
      const signature = await provider.request({
        method: "personal_sign",
        params: [nonceRes.message, address],
      }) as string;
      const verified = await authVerify(address, nonceRes.message, signature);
      setSessionAddress(verified.address);
    } catch (err: any) {
      setError(err?.message || "Sign-in failed");
      setSessionAddress(null);
    } finally {
      setAuthenticating(false);
    }
  }, [address]);

  const disconnect = useCallback(async () => {
    try {
      await authLogout();
    } catch {}
    setSessionAddress(null);
    setAddress(null);
    clearSelectedWalletProvider();
  }, []);

  const value = useMemo(
    () => ({
      address: address ?? null,
      sessionAddress: effectiveSessionAddress,
      connecting,
      authenticating,
      error,
      openConnectModal,
      signInWithEthereum,
      disconnect,
    }),
    [
      address,
      effectiveSessionAddress,
      connecting,
      authenticating,
      error,
      openConnectModal,
      signInWithEthereum,
      disconnect,
    ]
  );

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

export function useWallet(): WalletState {
  const ctx = useContext(WalletContext);
  if (!ctx) throw new Error("useWallet must be used within WalletProvider");
  return ctx;
}
