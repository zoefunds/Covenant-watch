"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Emblem } from "./Emblem";
import { useWallet } from "@/context/WalletContext";
import { shortAddr } from "@/lib/format";
import { Button } from "./ui";

const NAV = [
  { href: "/loans", label: "Loans" },
  { href: "/history", label: "History" },
  { href: "/profile", label: "Profile" },
  { href: "/settings", label: "Settings" },
];

export function Header() {
  const pathname = usePathname();
  const { address, sessionAddress, authenticating, error, openConnectModal, signInWithEthereum, disconnect } =
    useWallet();

  return (
    <header className="sticky top-0 z-20 border-b border-outline-variant bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <Emblem size={26} />
          <span className="text-sm font-semibold tracking-tight text-on-surface">Covenant Watch</span>
        </Link>
        <nav className="hidden items-center gap-1 sm:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`focus-ring rounded px-3 py-1.5 text-sm ${
                pathname?.startsWith(item.href)
                  ? "bg-surface-container-high text-on-surface"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          {sessionAddress ? (
            <div className="flex items-center gap-2">
              <span className="hidden font-onchain text-xs text-on-surface-variant sm:inline">
                {shortAddr(sessionAddress)}
              </span>
              <span className="h-2 w-2 rounded-full bg-tertiary-container" title="Session authenticated" />
              <Button variant="secondary" onClick={disconnect} className="!px-3 !py-1.5 text-xs">
                Sign out
              </Button>
            </div>
          ) : address ? (
            <div className="flex items-center gap-2">
              <span className="hidden font-onchain text-xs text-on-surface-variant sm:inline">{shortAddr(address)}</span>
              <Button onClick={signInWithEthereum} disabled={authenticating} className="!px-3 !py-1.5 text-xs">
                {authenticating ? "Sign to verify…" : "Sign in"}
              </Button>
            </div>
          ) : (
            <Button onClick={openConnectModal} className="!px-3 !py-1.5 text-xs">
              Connect wallet
            </Button>
          )}
        </div>
      </div>
      {error && (
        <div className="border-t border-error/30 bg-error-container/10 px-4 py-1.5 text-center text-xs text-error">
          {error}
        </div>
      )}
    </header>
  );
}
