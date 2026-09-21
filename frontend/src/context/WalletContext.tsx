"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useAppKit, useAppKitAccount, useAppKitProvider } from "@reown/appkit/react";
import { authMe, authNonce, authVerify, authLogout } from "@/lib/api";

interface EIP1193Provider {
  request: (args: { method: string; params?: any[] }) => Promise<any>;
}

interface WalletState {
  address: string | null; // connected wallet address (Reown AppKit) — connection only, not authenticated
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
  const { open } = useAppKit();
  const { address, isConnected } = useAppKitAccount();
  const { walletProvider } = useAppKitProvider<EIP1193Provider>("eip155");

  const [sessionAddress, setSessionAddress] = useState<string | null>(null);
  const [authenticating, setAuthenticating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connecting = false;

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
  const sessionMatchesWallet =
    isConnected && sessionAddress && address ? sessionAddress.toLowerCase() === address.toLowerCase() : isConnected;
  const effectiveSessionAddress = sessionMatchesWallet ? sessionAddress : null;

  const openConnectModal = useCallback(() => {
    setError(null);
    open();
  }, [open]);

  // Real SIWE-style round trip against the backend: nonce -> sign via the
  // AppKit-connected wallet's own provider -> verify. AppKit only got us a
  // connection; this is what actually authenticates the session.
  const signInWithEthereum = useCallback(async () => {
    if (!address || !walletProvider) {
      setError("Connect a wallet first.");
      return;
    }
    setError(null);
    setAuthenticating(true);
    try {
      const nonceRes = await authNonce(address);
      const signature: string = await walletProvider.request({
        method: "personal_sign",
        params: [nonceRes.message, address],
      });
      const verified = await authVerify(address, nonceRes.message, signature);
      setSessionAddress(verified.address);
    } catch (err: any) {
      setError(err?.message || "Sign-in failed");
      setSessionAddress(null);
    } finally {
      setAuthenticating(false);
    }
  }, [address, walletProvider]);

  const disconnect = useCallback(async () => {
    try {
      await authLogout();
    } catch {}
    setSessionAddress(null);
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
