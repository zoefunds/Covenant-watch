"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { Button, Card, ErrorState, LoadingState, Mono } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { SnapshotHash } from "@/components/SnapshotHash";
import { ConsensusMeter } from "@/components/ConsensusMeter";
import { TxStatusPanel } from "@/components/TxStatusPanel";
import { Countdown, useContractClock, useCountdown } from "@/components/Countdown";
import { useWallet } from "@/context/WalletContext";
import { useSigner } from "@/lib/useSigner";
import {
  getCovenant,
  getCovenantCheckHistory,
  getCooldownRemaining,
  triggerCovenantCheck,
  finalizeCovenantCheck,
  CovenantDict,
  CheckDict,
} from "@/lib/contract";
import { formatTs, formatDuration } from "@/lib/format";
import { runTrackedWrite, TxSnapshot } from "@/lib/tx";

export default function CheckPage() {
  const params = useParams<{ id: string; covenantId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const loanId = Number(params.id);
  const covenantId = Number(params.covenantId);
  const requestedCheckId = searchParams.get("checkId") ? Number(searchParams.get("checkId")) : null;

  const { sessionAddress } = useWallet();
  const signer = useSigner();

  const [covenant, setCovenant] = useState<CovenantDict | null>(null);
  const [history, setHistory] = useState<CheckDict[] | null>(null);
  const [cooldown, setCooldown] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [snap, setSnap] = useState<TxSnapshot>({ phase: "idle" });
  const [completedFinalizations, setCompletedFinalizations] = useState<Set<number>>(new Set());

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [cov, hist] = await Promise.all([getCovenant(covenantId), getCovenantCheckHistory(covenantId)]);
      setCovenant(cov);
      setHistory(hist);
      if (sessionAddress) {
        setCooldown(await getCooldownRemaining(loanId, covenantId, sessionAddress));
      }
    } catch (err: any) {
      setError(err.message);
    }
  }, [covenantId, loanId, sessionAddress]);

  useEffect(() => {
    if (Number.isFinite(covenantId)) reload();
  }, [covenantId, reload]);

  // Poll cooldown down to zero once it's known, real contract state only.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  async function trigger() {
    if (!signer) return;
    const result = await runTrackedWrite(() => triggerCovenantCheck(signer, loanId, covenantId), setSnap);
    if (result.phase === "finalized") await reload();
  }

  async function finalize(checkId: number) {
    if (!signer) return;
    const result = await runTrackedWrite(() => finalizeCovenantCheck(signer, loanId, checkId), setSnap);
    if (result.phase === "finalized") {
      setCompletedFinalizations((current) => new Set(current).add(checkId));
      await reload();
    }
  }

  const focusedCheck = requestedCheckId !== null
    ? history?.find((h) => h.id === requestedCheckId)
    : history?.[history.length - 1];
  const contractNow = useContractClock();
  const challengeRemaining = useCountdown(focusedCheck?.challenge_window_ends_at || 0, contractNow);

  if (!Number.isFinite(loanId) || !Number.isFinite(covenantId)) return <ErrorState body="Invalid loan/covenant id" />;
  if (error) return <div className="mx-auto max-w-3xl px-4 py-10"><ErrorState body={error} /></div>;
  if (!covenant || !history) return <div className="mx-auto max-w-3xl px-4 py-10"><LoadingState /></div>;

  const consensusVotes = (snap.result as any)?.consensus_data?.votes;
  const agree = Array.isArray(consensusVotes) ? consensusVotes.filter((v: any) => v?.vote === "AGREE" || v?.vote === "agree").length : null;
  const total = Array.isArray(consensusVotes) ? consensusVotes.length : null;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <p className="font-onchain text-xs text-on-surface-variant">
        Loan #{loanId} · Covenant #{covenantId}
      </p>
      <h1 className="mt-1 text-2xl font-semibold text-on-surface">{covenant.description}</h1>
      <p className="mt-1 font-onchain text-sm text-on-surface-variant">
        {covenant.source_type} · {covenant.condition_field} {covenant.operator} {covenant.threshold}
      </p>

      <Card className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-on-surface">Trigger a check</h2>
            <p className="mt-1 text-sm text-on-surface-variant">
              {cooldown > 0
                ? `Cooldown active — wait ${formatDuration(cooldown)} before this address can trigger again.`
                : "Snapshots the pinned source on-chain, then runs independent multi-validator evaluation."}
            </p>
          </div>
          <Button onClick={trigger} disabled={!signer || cooldown > 0 || snap.phase === "submitted" || snap.phase === "pending"}>
            {snap.phase === "submitted" || snap.phase === "pending" ? "Evaluating…" : "Trigger check"}
          </Button>
        </div>
        <div className="mt-3">
          <TxStatusPanel snap={snap} />
        </div>
      </Card>

      {focusedCheck && (
        <Card className="mt-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-on-surface">
              Check #{focusedCheck.id} {focusedCheck.id !== history[history.length - 1]?.id ? "" : "(latest)"}
            </h2>
            <StatusBadge status={focusedCheck.challenge_pending ? "CHALLENGE_ACTIVE" : focusedCheck.status} />
          </div>

          <div className="mt-4">
            <SnapshotHash
              sourceRef={covenant.source_ref}
              snapshotHash={focusedCheck.snapshot_hash}
              snapshotTs={focusedCheck.snapshot_ts}
            />
          </div>

          <div className="mt-4">
            <ConsensusMeter agree={agree} total={total} />
          </div>

          <div className="mt-4 space-y-1 text-sm">
            <p className="text-on-surface-variant">
              Observed value: <Mono className="text-on-surface">{focusedCheck.observed_value}</Mono>
            </p>
            {focusedCheck.observed_note && (
              <p className="text-on-surface-variant">
                Validator note: <span className="text-on-surface">{focusedCheck.observed_note}</span>
              </p>
            )}
            {focusedCheck.status === "BREACH" && (
              <div className="text-on-surface-variant">
                <p>Challenge window ends: <Mono className="text-on-surface">{formatTs(focusedCheck.challenge_window_ends_at)}</Mono></p>
                <p className="mt-1">Time remaining: <Mono className="text-on-surface"><Countdown targetTs={focusedCheck.challenge_window_ends_at} elapsedLabel="Closed — ready to finalize" nowTs={contractNow} /></Mono></p>
              </div>
            )}
          </div>

          {focusedCheck.status === "INCONCLUSIVE" && (
            <p className="mt-3 rounded border border-outline-variant bg-surface-container-high p-3 text-xs text-on-surface-variant">
              INCONCLUSIVE — the pinned source was unreachable or validators could not reach agreement. This is not
              a breach and not compliance; no consequence is applied.
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {focusedCheck.status === "BREACH" && !focusedCheck.finalized && (
              <>
                {challengeRemaining > 0 && covenant.source_type === "OFFCHAIN" && (
                  <Button href={`/loans/${loanId}/covenants/${covenantId}/challenge?checkId=${focusedCheck.id}`} variant="secondary">
                    Submit challenge evidence
                  </Button>
                )}
                <Button
                  onClick={() => finalize(focusedCheck.id)}
                  disabled={!signer || challengeRemaining > 0 || snap.phase === "submitted" || snap.phase === "pending" || completedFinalizations.has(focusedCheck.id)}
                >
                  {completedFinalizations.has(focusedCheck.id) ? "Check finalized" : challengeRemaining > 0 ? "Finalize after countdown" : "Finalize check"}
                </Button>
              </>
            )}
          </div>
        </Card>
      )}

      <h2 className="mt-8 mb-3 text-sm font-semibold text-on-surface">History for this covenant</h2>
      <div className="space-y-2">
        {history.length === 0 && <p className="text-sm text-on-surface-variant">No checks yet.</p>}
        {[...history].reverse().map((chk) => (
          <button key={chk.id} onClick={() => router.push(`/loans/${loanId}/covenants/${covenantId}/check?checkId=${chk.id}`)} className="block w-full text-left">
            <Card className="flex items-center justify-between transition-colors hover:border-primary-container/50">
              <div>
                <p className="text-sm text-on-surface">Check #{chk.id}</p>
                <p className="mt-1 font-onchain text-xs text-on-surface-variant">{formatTs(chk.evaluated_at)}</p>
              </div>
              <StatusBadge status={chk.challenge_pending ? "CHALLENGE_ACTIVE" : chk.status} />
            </Card>
          </button>
        ))}
      </div>
    </div>
  );
}
