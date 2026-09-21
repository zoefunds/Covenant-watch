"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button, Card, ErrorState, LoadingState, Mono } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { CollateralGauge } from "@/components/CollateralGauge";
import { TxStatusPanel } from "@/components/TxStatusPanel";
import { useWallet } from "@/context/WalletContext";
import { useSigner } from "@/lib/useSigner";
import {
  getLoan,
  getLoanCovenants,
  getCheckHistory,
  lockCollateral,
  claimPrincipal,
  repayLoan,
  cancelLoan,
  reclaimCollateralTimeout,
  claimSettlement,
  LoanDict,
  CovenantDict,
  CheckDict,
} from "@/lib/contract";
import { formatGen, formatBps, formatTs, shortAddr } from "@/lib/format";
import { runTrackedWrite, TxSnapshot } from "@/lib/tx";

export default function LoanDetailPage() {
  const params = useParams<{ id: string }>();
  const loanId = Number(params.id);
  const { sessionAddress } = useWallet();
  const signer = useSigner();

  const [loan, setLoan] = useState<LoanDict | null>(null);
  const [covenants, setCovenants] = useState<CovenantDict[] | null>(null);
  const [checks, setChecks] = useState<CheckDict[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [snap, setSnap] = useState<TxSnapshot>({ phase: "idle" });

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [l, c, h] = await Promise.all([getLoan(loanId), getLoanCovenants(loanId), getCheckHistory(loanId)]);
      setLoan(l);
      setCovenants(c);
      setChecks(h);
    } catch (err: any) {
      setError(err.message);
    }
  }, [loanId]);

  useEffect(() => {
    if (Number.isFinite(loanId)) reload();
  }, [loanId, reload]);

  const isLender = sessionAddress && loan && sessionAddress.toLowerCase() === loan.lender.toLowerCase();
  const isBorrower = sessionAddress && loan && sessionAddress.toLowerCase() === loan.borrower.toLowerCase();

  async function act(label: string, fn: () => Promise<any>) {
    if (!signer) return;
    await runTrackedWrite(fn, setSnap);
    await reload();
  }

  if (!Number.isFinite(loanId)) return <ErrorState body="Invalid loan id" />;
  if (error) return <div className="mx-auto max-w-4xl px-4 py-10"><ErrorState body={error} /></div>;
  if (!loan || !covenants || !checks) return <div className="mx-auto max-w-4xl px-4 py-10"><LoadingState /></div>;

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-onchain text-xs text-on-surface-variant">Loan #{loan.id}</p>
          <h1 className="mt-1 text-2xl font-semibold text-on-surface">{formatGen(loan.principal_wei)} principal</h1>
        </div>
        <StatusBadge status={loan.status} />
      </div>

      <Card className="mb-6">
        <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <p className="text-xs text-on-surface-variant">Lender</p>
            <Mono className="text-on-surface">{shortAddr(loan.lender)}</Mono>
          </div>
          <div>
            <p className="text-xs text-on-surface-variant">Borrower</p>
            <Mono className="text-on-surface">{shortAddr(loan.borrower)}</Mono>
          </div>
          <div>
            <p className="text-xs text-on-surface-variant">Current interest</p>
            <Mono className="text-on-surface">{formatBps(loan.current_interest_bps)}</Mono>
          </div>
          <div>
            <p className="text-xs text-on-surface-variant">Maturity</p>
            <Mono className="text-on-surface">{formatTs(loan.maturity_ts)}</Mono>
          </div>
        </div>
        <div className="mt-4">
          <CollateralGauge
            collateralWei={loan.collateral_deposited}
            principalWei={loan.principal_wei}
            breachTier={loan.breach_tier}
          />
        </div>
      </Card>

      {!sessionAddress && (
        <div className="mb-6 rounded border border-secondary/40 bg-secondary-container/10 p-4 text-sm text-on-surface-variant">
          Sign in to take actions on this loan.
        </div>
      )}

      <Card className="mb-6">
        <h2 className="mb-3 text-sm font-semibold text-on-surface">Actions</h2>
        <div className="flex flex-wrap gap-2">
          {isBorrower && loan.status === "CREATED" && (
            <Button onClick={() => act("lock", () => lockCollateral(signer!, loan.id, BigInt(loan.collateral_wei)))} disabled={!signer}>
              Lock collateral ({formatGen(loan.collateral_wei)})
            </Button>
          )}
          {isBorrower && loan.status !== "CREATED" && !loan.principal_claimed && (
            <Button onClick={() => act("claim-principal", () => claimPrincipal(signer!, loan.id))} disabled={!signer}>
              Claim principal
            </Button>
          )}
          {isLender && loan.status === "CREATED" && (
            <Button variant="secondary" onClick={() => act("cancel", () => cancelLoan(signer!, loan.id))} disabled={!signer}>
              Cancel loan (refund)
            </Button>
          )}
          {isBorrower && ["ACTIVE", "BREACH_TIER1", "BREACH_TIER2"].includes(loan.status) && (
            <Button
              variant="secondary"
              onClick={() =>
                act("repay", () =>
                  repayLoan(
                    signer!,
                    loan.id,
                    (BigInt(loan.principal_wei) * BigInt(10000 + loan.current_interest_bps)) / 10000n
                  )
                )
              }
              disabled={!signer}
            >
              Repay loan (principal + interest)
            </Button>
          )}
          {(isLender || isBorrower) && (
            <Button
              variant="secondary"
              onClick={() => act("reclaim-timeout", () => reclaimCollateralTimeout(signer!, loan.id))}
              disabled={!signer}
            >
              Reclaim on counterparty timeout
            </Button>
          )}
          {(isLender || isBorrower) && (loan.claimable_lender_wei > 0 || loan.claimable_borrower_wei > 0) && (
            <Button onClick={() => act("claim-settlement", () => claimSettlement(signer!, loan.id))} disabled={!signer}>
              Claim settlement (
              {formatGen(isLender ? loan.claimable_lender_wei : loan.claimable_borrower_wei)})
            </Button>
          )}
        </div>
        <div className="mt-3">
          <TxStatusPanel snap={snap} />
        </div>
      </Card>

      <h2 className="mb-3 text-sm font-semibold text-on-surface">Covenants</h2>
      <div className="mb-8 space-y-3">
        {covenants.map((cov) => (
          <Card key={cov.id} className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-on-surface">{cov.description}</p>
              <p className="mt-1 font-onchain text-xs text-on-surface-variant">
                {cov.source_type} · {cov.condition_field} {cov.operator} {cov.threshold} · {cov.confirmed_breach_count}{" "}
                confirmed breach(es)
              </p>
            </div>
            <div className="flex gap-2">
              <Button href={`/loans/${loan.id}/covenants/${cov.id}/check`} variant="secondary" className="!px-3 !py-1.5 text-xs">
                Check
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <h2 className="mb-3 text-sm font-semibold text-on-surface">Check history</h2>
      {checks.length === 0 ? (
        <p className="text-sm text-on-surface-variant">No checks triggered yet.</p>
      ) : (
        <div className="space-y-2">
          {checks.map((chk) => (
            <Link key={chk.id} href={`/loans/${loan.id}/covenants/${chk.covenant_id}/check?checkId=${chk.id}`}>
              <Card className="flex items-center justify-between transition-colors hover:border-primary-container/50">
                <div>
                  <p className="text-sm text-on-surface">Check #{chk.id} · Covenant #{chk.covenant_id}</p>
                  <p className="mt-1 font-onchain text-xs text-on-surface-variant">{formatTs(chk.evaluated_at)}</p>
                </div>
                <StatusBadge status={chk.challenge_pending ? "CHALLENGE_ACTIVE" : chk.status} />
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
