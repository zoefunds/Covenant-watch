"use client";

import { Emblem } from "@/components/Emblem";
import { Button, Card } from "@/components/ui";
import { useWallet } from "@/context/WalletContext";
import { CONTRACT_ADDRESS, GENLAYER_NETWORK } from "@/lib/config";
import { shortAddr } from "@/lib/format";
import Link from "next/link";

const LOOP = [
  { title: "Loan + covenants", body: "Lender defines principal, checkable covenants, and a graduated consequence schedule." },
  { title: "Locked collateral", body: "Borrower escrows the exact GEN collateral amount before drawing principal." },
  { title: "Check trigger", body: "Either party triggers a covenant check; the pinned source is snapshotted on-chain first." },
  { title: "Validator inspection", body: "GenLayer validators independently fetch or read the pinned source." },
  { title: "Equivalence", body: "Structured results are compared with numeric tolerance — not a brittle exact-match." },
  { title: "Consequence", body: "A confirmed breach applies the precommitted tier: rate step-up, partial seizure, or default." },
  { title: "Challenge window", body: "A bounded window allows additive evidence before the result finalizes." },
  { title: "Finalized", body: "Funds settle via pull-based claims once the window closes." },
];

export default function LandingPage() {
  const { sessionAddress, address, openConnectModal, signInWithEthereum, authenticating } = useWallet();

  return (
    <div>
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24">
        <div className="flex flex-col items-start gap-6">
          <Emblem size={48} />
          <h1 className="max-w-2xl text-3xl font-semibold tracking-tight text-on-surface sm:text-5xl">
            Covenants that enforce themselves.
          </h1>
          <p className="max-w-xl text-base text-on-surface-variant sm:text-lg">
            Covenant Watch precommits checkable loan covenants on GenLayer. Validators independently verify
            compliance and apply a graduated, precommitted consequence — no discretionary judgment calls, no
            vague terms.
          </p>
          <div className="flex flex-wrap gap-3">
            {sessionAddress ? (
              <Button href="/loans">Go to your loans</Button>
            ) : address ? (
              <Button onClick={signInWithEthereum} disabled={authenticating}>
                {authenticating ? "Sign to verify…" : "Sign in to begin"}
              </Button>
            ) : (
              <Button onClick={openConnectModal}>Connect wallet to begin</Button>
            )}
            <Button href="/loans/new" variant="secondary">
              Originate a loan
            </Button>
          </div>
          <p className="font-onchain text-xs text-on-surface-variant">
            Deployed contract ({GENLAYER_NETWORK}):{" "}
            <Link href={`/settings`} className="text-primary-container underline">
              {shortAddr(CONTRACT_ADDRESS, 6)}
            </Link>
          </p>
        </div>
      </section>

      <section className="border-t border-outline-variant bg-surface-container-lowest">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
          <h2 className="mb-8 text-lg font-semibold text-on-surface">The core loop</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {LOOP.map((step, i) => (
              <Card key={step.title} className="flex flex-col gap-2">
                <span className="font-onchain text-xs text-primary-container">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="text-sm font-semibold text-on-surface">{step.title}</h3>
                <p className="text-sm text-on-surface-variant">{step.body}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <Card>
            <h3 className="text-sm font-semibold text-on-surface">Real validator consensus</h3>
            <p className="mt-2 text-sm text-on-surface-variant">
              Every check is evaluated independently by multiple GenLayer validators and compared with structured
              equivalence — status match plus numeric tolerance, never a fragile exact-string match.
            </p>
          </Card>
          <Card>
            <h3 className="text-sm font-semibold text-on-surface">INCONCLUSIVE is a real state</h3>
            <p className="mt-2 text-sm text-on-surface-variant">
              An unreachable source or disagreeing validators route to a genuine third state — never silently
              guessed as compliant or in breach.
            </p>
          </Card>
          <Card>
            <h3 className="text-sm font-semibold text-on-surface">Additive-only challenges</h3>
            <p className="mt-2 text-sm text-on-surface-variant">
              The original pinned source can never be edited or replaced. A challenge can only add evidence within
              a bounded window before finalization.
            </p>
          </Card>
        </div>
      </section>
    </div>
  );
}
