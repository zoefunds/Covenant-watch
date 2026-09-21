"use client";

// Wallet connection state (Reown AppKit) is inherently client/runtime
// only — there is nothing meaningful to server-render for "is a wallet
// connected", and AppKit's hooks throw if createAppKit hasn't run yet
// (which never happens during the build's static prerender pass, since
// window is undefined there). Rendered only after mount so AppKit is
// guaranteed initialized first — see lib/appkit.ts's module-scope
// ensureAppKit() call.

import React, { useEffect, useState } from "react";
import { Providers } from "./Providers";
import { Header } from "./Header";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-on-surface-variant">
        Loading Covenant Watch…
      </div>
    );
  }

  return (
    <Providers>
      <Header />
      <main className="flex-1">{children}</main>
      <footer className="border-t border-outline-variant px-4 py-6 text-center text-xs text-on-surface-variant sm:px-6">
        Covenant Watch — GenLayer StudioNet. Contract reads/writes go directly to the chain; the backend is a read
        cache for history and profile views only.
      </footer>
    </Providers>
  );
}
