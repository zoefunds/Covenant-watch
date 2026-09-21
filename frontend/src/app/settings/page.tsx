"use client";

import { useEffect, useState } from "react";
import { Card, Mono } from "@/components/ui";
import { useWallet } from "@/context/WalletContext";
import { CONTRACT_ADDRESS, GENLAYER_NETWORK, BACKEND_URL, GENLAYER_EXPLORER_URL } from "@/lib/config";
import { healthz } from "@/lib/api";

export default function SettingsPage() {
  const { sessionAddress, disconnect } = useWallet();
  const [health, setHealth] = useState<any>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    healthz()
      .then(setHealth)
      .catch((err) => setHealthError(err.message));
  }, []);

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl font-semibold text-on-surface">Settings</h1>

      <Card className="mt-6">
        <h2 className="text-sm font-semibold text-on-surface">Network</h2>
        <dl className="mt-3 space-y-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-on-surface-variant">GenLayer network</dt>
            <dd className="font-onchain text-on-surface">{GENLAYER_NETWORK}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-on-surface-variant">Contract address</dt>
            <dd className="font-onchain break-all text-right text-on-surface">{CONTRACT_ADDRESS}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-on-surface-variant">Explorer</dt>
            <dd>
              <a href={GENLAYER_EXPLORER_URL} target="_blank" rel="noreferrer" className="text-primary-container underline">
                {GENLAYER_EXPLORER_URL}
              </a>
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-on-surface-variant">Backend API</dt>
            <dd className="font-onchain break-all text-right text-on-surface">{BACKEND_URL}</dd>
          </div>
        </dl>
      </Card>

      <Card className="mt-4">
        <h2 className="text-sm font-semibold text-on-surface">Backend health</h2>
        {healthError && <p className="mt-2 text-sm text-error">{healthError}</p>}
        {health && (
          <pre className="mt-2 overflow-x-auto rounded bg-surface-container-lowest p-3 font-onchain text-xs text-on-surface-variant">
            {JSON.stringify(health, null, 2)}
          </pre>
        )}
      </Card>

      <Card className="mt-4">
        <h2 className="text-sm font-semibold text-on-surface">Session</h2>
        <p className="mt-2 text-sm text-on-surface-variant">
          {sessionAddress ? (
            <>
              Signed in as <Mono className="text-on-surface">{sessionAddress}</Mono>.
            </>
          ) : (
            "Not signed in."
          )}
        </p>
        {sessionAddress && (
          <button onClick={disconnect} className="focus-ring mt-3 rounded bg-error-container px-4 py-2 text-sm text-on-error-container">
            Sign out (clears backend session)
          </button>
        )}
      </Card>

      <Card className="mt-4">
        <h2 className="text-sm font-semibold text-on-surface">Deferred (out of v1 scope)</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-on-surface-variant">
          <li>Custom RPC endpoint override — currently fixed to the configured GenLayer network&apos;s default RPC.</li>
          <li>Email/push notifications on covenant check results — not built; the app relies on you checking a loan page.</li>
          <li>Multi-account / team access on a single loan — each loan&apos;s lender/borrower is a single address, per the contract.</li>
        </ul>
      </Card>
    </div>
  );
}
