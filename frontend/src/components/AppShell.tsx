"use client";

// Browser-wallet connection and provider selection are owned by the client
// context below. No connector SDK or custodial signer sits in between.

import React from "react";
import { Providers } from "./Providers";
import { Header } from "./Header";
import { WalletPicker } from "./WalletPicker";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <WalletPicker />
      <Header />
      <main className="flex-1">{children}</main>
      <footer className="border-t border-outline-variant px-4 py-6 text-center text-xs text-on-surface-variant sm:px-6">
        Covenant Watch — GenLayer StudioNet. Contract reads/writes go directly to the chain; the backend is a read
        cache for history and profile views only.
      </footer>
    </Providers>
  );
}
