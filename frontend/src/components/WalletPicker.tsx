"use client";

import { useEffect, useState } from "react";
import { registerWalletPicker, WalletProvider } from "@/lib/walletProviders";
import { Button, Card } from "./ui";

export function WalletPicker() {
  const [wallets, setWallets] = useState<WalletProvider[]>([]);
  const [resolveChoice, setResolveChoice] = useState<((wallet: WalletProvider) => void) | null>(null);

  useEffect(() => {
    registerWalletPicker((choices) => new Promise<WalletProvider>((resolve) => {
      setWallets(choices);
      setResolveChoice(() => resolve);
    }));
    return () => registerWalletPicker(null);
  }, []);

  if (!resolveChoice) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 px-4">
      <Card className="w-full max-w-sm p-6">
        <p className="font-onchain text-xs uppercase tracking-wider text-primary-container">Wallet provider</p>
        <h2 className="mt-2 mb-5 text-xl font-semibold text-on-surface">Choose a wallet</h2>
        <div className="space-y-3">
          {wallets.map((wallet) => (
            <Button key={wallet.info.uuid} variant="secondary" className="flex w-full items-center justify-start gap-3" onClick={() => {
              resolveChoice(wallet);
              setResolveChoice(null);
              setWallets([]);
            }}>
              {wallet.info.icon ? (
                // EIP-6963 icons are wallet-extension-supplied data URIs.
                // eslint-disable-next-line @next/next/no-img-element
                <img src={wallet.info.icon} alt="" className="h-7 w-7 rounded" />
              ) : <span>◈</span>}
              {wallet.info.name}
            </Button>
          ))}
        </div>
      </Card>
    </div>
  );
}
