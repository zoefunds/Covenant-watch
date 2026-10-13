"use client";

import { useEffect, useState } from "react";
import { listLoans } from "@/lib/api";
import { Button, Card, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { CollateralGauge } from "@/components/CollateralGauge";
import { Countdown, useContractClock } from "@/components/Countdown";
import { formatUsdc, formatBps, formatTs, shortAddr } from "@/lib/format";
import { useWallet } from "@/context/WalletContext";
import milestoneData from "@/data/milestoneScenarios.json";
import Link from "next/link";

const baseStatusNames = ["CREATED", "ACTIVE", "BREACH_TIER1", "BREACH_TIER2", "DEFAULTED", "REPAID", "CANCELLED", "TIMEOUT_RECLAIMED"];

export default function LoansPage() {
  const contractNow = useContractClock();
  const { sessionAddress } = useWallet();
  const [loans, setLoans] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "mine">("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "compliant" | "grace" | "breach">("all");

  useEffect(() => {
    let cancelled = false;
    setLoans(null);
    setError(null);
    const refresh = async (initial = false) => {
      try {
        // Loan-list polling is deliberately backend-only. An empty response
        // is a valid fresh-contract state, not a reason for every browser to
        // start reading GenLayer RPC directly.
        const loadLoans = () => listLoans();
        if (filter === "mine" && sessionAddress) {
          const allLoans = await loadLoans();
          if (!cancelled) {
            setLoans(allLoans.filter((l) =>
              (l.lender_address ?? l.lender)?.toLowerCase() === sessionAddress.toLowerCase() ||
              (l.borrower_address ?? l.borrower)?.toLowerCase() === sessionAddress.toLowerCase()
            ));
          }
        } else {
          if (!cancelled) setLoans(await loadLoans());
        }
      } catch (err: any) {
        if (initial && !cancelled) setError(err.message);
      }
    };
    // Poll the backend read cache; the backend indexer is responsible for
    // keeping this view synchronized with the contract.
    refresh(true);
    const timer = window.setInterval(() => refresh(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [filter, sessionAddress]);

  function statusBucket(status: string): "compliant" | "grace" | "breach" {
    if (status === "BREACH_TIER1" || status === "BREACH_TIER2" || status === "DEFAULTED") return "breach";
    if (status === "CHALLENGE_ACTIVE") return "grace";
    return "compliant";
  }

  const visibleLoans = loans?.filter((l) => statusFilter === "all" || statusBucket(l.status) === statusFilter) ?? null;
  const counts = loans
    ? {
        all: loans.length,
        compliant: loans.filter((l) => statusBucket(l.status) === "compliant").length,
        grace: loans.filter((l) => statusBucket(l.status) === "grace").length,
        breach: loans.filter((l) => statusBucket(l.status) === "breach").length,
        escrowed: loans.reduce((sum, l) => sum + Number(l.collateral_deposited ?? 0), 0),
      }
    : null;

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

      {counts && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card className="!p-3">
            <p className="font-onchain text-[10px] uppercase text-on-surface-variant">Total escrowed</p>
            <p className="mt-1 text-lg font-semibold text-on-surface">{formatUsdc(counts.escrowed)}</p>
          </Card>
          <Card className="!p-3">
            <p className="font-onchain text-[10px] uppercase text-on-surface-variant">Loans</p>
            <p className="mt-1 text-lg font-semibold text-on-surface">{counts.all}</p>
          </Card>
          <Card className="!p-3">
            <p className="font-onchain text-[10px] uppercase text-on-surface-variant">In grace / challenge</p>
            <p className="mt-1 text-lg font-semibold text-secondary">{counts.grace}</p>
          </Card>
          <Card className="!p-3">
            <p className="font-onchain text-[10px] uppercase text-on-surface-variant">Breached</p>
            <p className="mt-1 text-lg font-semibold text-error">{counts.breach}</p>
          </Card>
        </div>
      )}

      {loans && loans.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          {(["all", "compliant", "grace", "breach"] as const).map((b) => (
            <button
              key={b}
              onClick={() => setStatusFilter(b)}
              className={`rounded px-3 py-1.5 capitalize ${
                statusFilter === b ? "bg-surface-container-high text-on-surface" : "bg-surface-container text-on-surface-variant"
              }`}
            >
              {b} {counts ? `(${b === "all" ? counts.all : counts[b]})` : ""}
            </button>
          ))}
        </div>
      )}

      {loans === null && !error && <LoadingState label="Loading loans…" />}
      {error && <ErrorState body={error} />}
      {loans && loans.length === 0 && (
        <EmptyState
          title={filter === "mine" ? "No loans involving your address yet" : "No loans yet"}
          body="Origination writes directly to the contract; once indexed it will appear here."
          action={<Button href="/loans/new">Originate the first loan</Button>}
        />
      )}
      {visibleLoans && visibleLoans.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {visibleLoans.map((loan) => (
            <Link key={loan.chain_loan_id} href={`/loans/${loan.chain_loan_id}`}>
              <Card className="h-full transition-colors hover:border-primary-container/50">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-onchain text-xs text-on-surface-variant">Loan #{loan.chain_loan_id}</p>
                    <p className="mt-1 text-lg font-semibold text-on-surface">{formatUsdc(loan.principal_wei)}</p>
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
                  <p>
                    Maturity countdown: <span className="font-onchain text-on-surface"><Countdown targetTs={loan.maturity_ts} elapsedLabel="Matured" nowTs={contractNow} /></span>
                  </p>
                </div>
                <div className="mt-4">
                  <CollateralGauge
                    collateralWei={loan.collateral_deposited}
                    principalWei={loan.principal_wei}
                    breachTier={loan.status?.startsWith("BREACH_TIER2") ? 2 : loan.status?.startsWith("BREACH_TIER1") ? 1 : loan.status === "DEFAULTED" ? 3 : 0}
                  />
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <section className="mt-12 border-t border-outline-variant pt-8">
        <p className="font-onchain text-xs uppercase tracking-widest text-primary-container">Verified on Base Sepolia</p>
        <h2 className="mt-2 text-2xl font-semibold text-on-surface">Live E2E test loans</h2>
        <p className="mt-2 max-w-3xl text-sm text-on-surface-variant">
          These three loans use real USDC escrow transactions—not placeholder data. Open a loan or inspect each
          confirmed transaction on BaseScan.
        </p>
        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          {milestoneData.scenarios.map((item) => (
            <Card key={item.scenario} className="h-full">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-onchain text-xs text-primary-container">Test {item.scenario} · Loan #{item.loanId}</p>
                  <h3 className="mt-2 text-lg font-semibold text-on-surface">{item.title}</h3>
                </div>
                <StatusBadge status={baseStatusNames[item.finalState.status]} />
              </div>
              <p className="mt-2 text-sm text-on-surface-variant">{item.summary}</p>
              <dl className="mt-4 space-y-2 text-xs text-on-surface-variant">
                <div className="flex justify-between gap-3"><dt>Principal</dt><dd className="text-on-surface">{formatUsdc(item.finalState.principal)}</dd></div>
                <div className="flex justify-between gap-3"><dt>Collateral remaining</dt><dd className="text-on-surface">{formatUsdc(item.finalState.collateralEscrowed)}</dd></div>
                <div className="flex justify-between gap-3"><dt>Breach tier</dt><dd className="text-on-surface">{item.finalState.breachTier}</dd></div>
                <div className="flex justify-between gap-3"><dt>Current interest</dt><dd className="text-on-surface">{(item.finalState.currentInterestBps / 100).toFixed(2)}%</dd></div>
              </dl>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href={`/loans/${item.loanId}`} className="rounded bg-primary-container px-2 py-1 font-onchain text-[10px] text-on-primary-container">
                  Open loan
                </Link>
                {Object.entries(item.transactions).flatMap(([event, hashes]) => (hashes as string[]).map((hash, i) => (
                  <a key={`${event}-${hash}`} href={`https://sepolia.basescan.org/tx/${hash.startsWith("0x") ? hash : `0x${hash}`}`} target="_blank" rel="noreferrer" className="rounded border border-outline/30 px-2 py-1 font-onchain text-[10px] text-primary-container hover:border-primary-container">
                    {event}{hashes.length > 1 ? ` ${i + 1}` : ""}
                  </a>
                )))}
              </div>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
