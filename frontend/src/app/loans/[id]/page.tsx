"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button, Card, ErrorState, LoadingState, Mono } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { CollateralGauge } from "@/components/CollateralGauge";
import { TxStatusPanel } from "@/components/TxStatusPanel";
import { Countdown, useContractClock } from "@/components/Countdown";
import { useWallet } from "@/context/WalletContext";
import { useSigner } from "@/lib/useSigner";
import {
  activateBaseLoan,
  getLoan,
  getLoanCovenants,
  getCheckHistory,
  LoanDict,
  CovenantDict,
  CheckDict,
} from "@/lib/contract";
import { getLoanCached, getLoanCovenantsCached, getLoanChecksCached, getBaseLoan } from "@/lib/api";
import { formatUsdc, formatBps, formatTs, shortAddr } from "@/lib/format";
import { stakeBaseCollateral, claimBasePrincipal, claimBaseSettlement, repayBaseLoan } from "@/lib/base";
import { runTrackedWrite, TxSnapshot } from "@/lib/tx";

function timestampSeconds(value: unknown): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : 0;
  }
  return 0;
}

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
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [completedActions, setCompletedActions] = useState<Set<string>>(new Set());
  const [principalClaimReady, setPrincipalClaimReady] = useState(false);

  const reload = useCallback(async (direct = false) => {
    setError(null);
    try {
      let l: any;
      let c: any[];
      let h: any[];
      try {
        if (direct) throw new Error("read finalized state directly");
        [l, c, h] = await Promise.all([
          getLoanCached(loanId),
          getLoanCovenantsCached(loanId),
          getLoanChecksCached(loanId),
        ]);
      } catch {
        // The backend may not have indexed a just-created loan yet. Read the
        // same state directly from the contract until the cache catches up.
        [l, c, h] = await Promise.all([
          getLoan(loanId),
          getLoanCovenants(loanId),
          getCheckHistory(loanId),
        ]);
      }
      const base = await getBaseLoan(loanId);
      const statuses = ["CREATED", "ACTIVE", "BREACH_TIER1", "BREACH_TIER2", "DEFAULTED", "REPAID", "CANCELLED", "TIMEOUT_RECLAIMED"];
      setPrincipalClaimReady([1, 2, 3].includes(Number(base.status)));
      setLoan({
        id: l.chain_loan_id ?? l.id,
        lender: l.lender_address ?? l.lender,
        borrower: l.borrower_address ?? l.borrower,
        principal_wei: BigInt(base.principal),
        collateral_wei: BigInt(base.collateral_required),
        collateral_deposited: BigInt(base.collateral_escrowed),
        current_interest_bps: base.current_interest_bps,
        maturity_ts: l.maturity_ts,
        status: statuses[Number(base.status)] ?? l.status,
        breach_tier: Number(base.breach_tier),
        principal_claimed: Boolean(base.principal_claimed),
        claimable_lender_wei: BigInt(base.lender_claimable),
        claimable_borrower_wei: BigInt(base.borrower_claimable),
        challenge_window_seconds: l.challenge_window_seconds ?? 0,
      } as unknown as LoanDict);
      // Cache records use database IDs and compact nested fields; contract
      // reads use chain IDs and flat fields. Normalize both into the shape
      // consumed by this page so links always carry chain IDs.
      setCovenants(c.map((cov) => ({
        ...cov,
        id: cov.chain_covenant_id ?? cov.id,
        loan_id: cov.chain_loan_id ?? loanId,
        source_type: String(cov.source_type || "OFFCHAIN").toUpperCase(),
        condition_field: cov.condition_field ?? cov.condition_spec?.condition_field ?? "",
        operator: cov.operator ?? cov.condition_spec?.operator ?? "",
        threshold: String(cov.threshold ?? cov.condition_spec?.threshold ?? "—"),
        description: cov.description ?? cov.source_ref ?? "Covenant",
        tier1_interest_step_up_bps: cov.tier1_interest_step_up_bps ?? 0,
        tier2_seizure_bps: cov.tier2_seizure_bps ?? 0,
        confirmed_breach_count: cov.confirmed_breach_count ?? 0,
        last_check_id: cov.last_check_id ?? 0,
      })) as CovenantDict[]);
      setChecks(h.map((check) => ({
        ...check,
        id: check.chain_check_id ?? check.id,
        loan_id: check.chain_loan_id ?? loanId,
        covenant_id: check.chain_covenant_id ?? check.covenant_id,
        snapshot_ts: check.snapshot_ts ?? timestampSeconds(check.triggered_at),
        status: String(check.status || "PENDING").toUpperCase(),
        observed_value: check.observed_value ?? check.validator_result?.observed_value ?? "",
        observed_note: check.observed_note ?? check.validator_result?.observed_note ?? "",
        result_source_hash: check.result_source_hash ?? check.validator_result?.result_source_hash ?? "",
        evaluated_at: check.evaluated_at ?? timestampSeconds(check.finalized_at || check.triggered_at),
        challenge_count: check.challenge_count ?? 0,
        challenge_pending: check.challenge_pending ?? false,
        finalized: check.finalized ?? Boolean(check.finalized_at),
      })) as CheckDict[]);
      return true;
    } catch (err: any) {
      setError(err.message);
      return false;
    }
  }, [loanId]);

  useEffect(() => {
    if (!Number.isFinite(loanId)) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      const succeeded = await reload();
      // Do not keep spending RPC capacity retrying a definitively invalid
      // route. A real loan page continues polling after a successful read.
      if (succeeded && !cancelled) timer = window.setTimeout(poll, 10000);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [loanId, reload]);

  const isLender = sessionAddress && loan && sessionAddress.toLowerCase() === loan.lender.toLowerCase();
  const isBorrower = sessionAddress && loan && sessionAddress.toLowerCase() === loan.borrower.toLowerCase();
  const contractNow = useContractClock();

  async function act(label: string, fn: () => Promise<any>) {
    if (!signer) return;
    setActiveAction(label);
    const result = await runTrackedWrite(fn, setSnap);
    if (result.phase === "finalized") {
      setCompletedActions((current) => new Set(current).add(label));
      // Finality was just observed by the RPC. Bypass the eventually
      // consistent backend cache so the screen changes immediately.
      await reload(true);
    }
    setActiveAction(null);
  }

  async function actBase(label: string, fn: () => Promise<`0x${string}`>) {
    if (!signer) return;
    setActiveAction(label);
    setSnap({ phase: "submitted" });
    try {
      const hash = await fn();
      setSnap({ phase: "finalized", hash, statusName: "CONFIRMED_ON_BASE_SEPOLIA" });
      setCompletedActions((current) => new Set(current).add(label));
      await reload(true);
    } catch (err: any) {
      setSnap({ phase: "failed", error: err?.message || String(err) });
    }
    setActiveAction(null);
  }

  if (!Number.isFinite(loanId)) return <ErrorState body="Invalid loan id" />;
  if (error) return <div className="mx-auto max-w-4xl px-4 py-10"><ErrorState body={error} /></div>;
  if (!loan || !covenants || !checks) return <div className="mx-auto max-w-4xl px-4 py-10"><LoadingState /></div>;

  const writeBusy = activeAction !== null;
  const actionDisabled = (key: string) => !signer || writeBusy || completedActions.has(key);

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-onchain text-xs text-on-surface-variant">Loan #{loan.id}</p>
          <h1 className="mt-1 text-2xl font-semibold text-on-surface">{formatUsdc(loan.principal_wei)} principal</h1>
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
            <p className="mt-1 text-xs text-on-surface-variant">
              <Countdown targetTs={loan.maturity_ts} elapsedLabel="Matured" nowTs={contractNow} />
            </p>
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
            <Button onClick={() => act("lock", async () => {
              const amount = formatUsdc(loan.collateral_wei).replace(" USDC", "");
              const baseHash = await stakeBaseCollateral(signer!, loan.id, amount);
              return activateBaseLoan(signer!, loan.id, baseHash);
            })} disabled={actionDisabled("lock")}>
              {completedActions.has("lock") ? "Collateral staked" : `Stake collateral (${formatUsdc(loan.collateral_wei)})`}
            </Button>
          )}
          {isBorrower && ["ACTIVE", "BREACH_TIER1", "BREACH_TIER2"].includes(loan.status) && !loan.principal_claimed && (
            <div className="flex flex-col gap-1">
              <Button
                onClick={() => actBase("claim-principal", () => claimBasePrincipal(signer!, loan.id))}
                disabled={actionDisabled("claim-principal") || !principalClaimReady}
              >
                {completedActions.has("claim-principal")
                  ? "Principal claimed"
                  : principalClaimReady
                    ? "Claim principal"
                    : "Complete covenant checks first"}
              </Button>
              {!principalClaimReady && (
                <span className="max-w-64 text-xs text-on-surface-variant">
                  Every covenant needs a latest finalized COMPLIANT check before the contract permits this draw.
                </span>
              )}
            </div>
          )}
          {isBorrower && loan.principal_claimed && ["ACTIVE", "BREACH_TIER1", "BREACH_TIER2"].includes(loan.status) && (
            <Button
              variant="secondary"
              onClick={() =>
                actBase("repay", () =>
                  repayBaseLoan(
                    signer!,
                    loan.id,
                    (BigInt(loan.principal_wei) * BigInt(10000 + loan.current_interest_bps)) / 10000n
                  )
                )
              }
              disabled={actionDisabled("repay")}
            >
              {completedActions.has("repay") ? "Loan repaid" : "Repay loan (principal + interest)"}
            </Button>
          )}
          {(isLender || isBorrower) && (loan.claimable_lender_wei > 0 || loan.claimable_borrower_wei > 0) && (
            <Button onClick={() => actBase("claim-settlement", () => claimBaseSettlement(signer!, loan.id))} disabled={actionDisabled("claim-settlement")}>
              {completedActions.has("claim-settlement") ? "Settlement claimed" : <>Claim settlement (
              {formatUsdc(isLender ? loan.claimable_lender_wei : loan.claimable_borrower_wei)})
              </>}
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
