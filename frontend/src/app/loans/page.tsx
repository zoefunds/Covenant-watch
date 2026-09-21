"use client";

import { useEffect, useState } from "react";
import { listLoans } from "@/lib/api";
import { Button, Card, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { CollateralGauge } from "@/components/CollateralGauge";
import { formatGen, formatBps, formatTs, shortAddr } from "@/lib/format";
import { useWallet } from "@/context/WalletContext";
import Link from "next/link";

export default function LoansPage() {
  const { sessionAddress } = useWallet();
  const [loans, setLoans] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "mine">("all");

  useEffect(() => {
    setLoans(null);
    setError(null);
    // The backend only supports one of lender/borrower per request; when
    // "mine" is selected we fetch both roles and merge, deduping by id.
    (async () => {
      try {
        if (filter === "mine" && sessionAddress) {
          const [asLender, asBorrower] = await Promise.all([
            listLoans({ lender: sessionAddress }),
            listLoans({ borrower: sessionAddress }),
          ]);
          const byId = new Map<number, any>();
          [...asLender, ...asBorrower].forEach((l) => byId.set(l.chain_loan_id, l));
          setLoans([...byId.values()]);
        } else {
          setLoans(await listLoans());
        }
      } catch (err: any) {
        setError(err.message);
      }
    })();
  }, [filter, sessionAddress]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-on-surface">Active credit lines</h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            Sourced from the backend read cache. Live contract state is always checked before any fund-critical
            action.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded border border-outline-variant p-0.5 text-xs">
            <button
              onClick={() => setFilter("all")}
              className={`rounded px-3 py-1.5 ${filter === "all" ? "bg-surface-container-high text-on-surface" : "text-on-surface-variant"}`}
            >
              All
            </button>
            <button
              onClick={() => setFilter("mine")}
              disabled={!sessionAddress}
              className={`rounded px-3 py-1.5 disabled:opacity-40 ${filter === "mine" ? "bg-surface-container-high text-on-surface" : "text-on-surface-variant"}`}
            >
              Mine
            </button>
          </div>
          <Button href="/loans/new">Originate loan</Button>
        </div>
      </div>

      {loans === null && !error && <LoadingState label="Loading loans…" />}
      {error && <ErrorState body={error} />}
      {loans && loans.length === 0 && (
        <EmptyState
          title={filter === "mine" ? "No loans involving your address yet" : "No loans yet"}
          body="Origination writes directly to the contract; once indexed it will appear here."
          action={<Button href="/loans/new">Originate the first loan</Button>}
        />
      )}
      {loans && loans.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {loans.map((loan) => (
            <Link key={loan.chain_loan_id} href={`/loans/${loan.chain_loan_id}`}>
              <Card className="h-full transition-colors hover:border-primary-container/50">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-onchain text-xs text-on-surface-variant">Loan #{loan.chain_loan_id}</p>
                    <p className="mt-1 text-lg font-semibold text-on-surface">{formatGen(loan.principal_wei)}</p>
                  </div>
                  <StatusBadge status={loan.status} />
                </div>
                <div className="mt-3 space-y-1 text-xs text-on-surface-variant">
                  <p>
                    Lender <span className="font-onchain text-on-surface">{shortAddr(loan.lender_address)}</span> ·
                    Borrower <span className="font-onchain text-on-surface">{shortAddr(loan.borrower_address)}</span>
                  </p>
                  <p>
                    Interest {formatBps(loan.interest_bps)} · Matures {formatTs(loan.maturity_ts)}
                  </p>
                </div>
                <div className="mt-4">
                  <CollateralGauge
                    collateralWei={Number(loan.collateral_deposited)}
                    principalWei={Number(loan.principal_wei)}
                    breachTier={loan.status?.startsWith("BREACH_TIER2") ? 2 : loan.status?.startsWith("BREACH_TIER1") ? 1 : loan.status === "DEFAULTED" ? 3 : 0}
                  />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
