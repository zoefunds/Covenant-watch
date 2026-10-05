"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Button, Card, ErrorState, Field, Input, LoadingState, TextArea, Mono } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { TxStatusPanel } from "@/components/TxStatusPanel";
import { Countdown, useContractClock, useCountdown } from "@/components/Countdown";
import { useSigner } from "@/lib/useSigner";
import { getCheck, getChallengeState, submitChallengeEvidence, CheckDict } from "@/lib/contract";
import { formatTs } from "@/lib/format";
import { runTrackedWrite, TxSnapshot } from "@/lib/tx";

export default function ChallengePage() {
  const params = useParams<{ id: string; covenantId: string }>();
  const searchParams = useSearchParams();
  const loanId = Number(params.id);
  const covenantId = Number(params.covenantId);
  const checkId = Number(searchParams.get("checkId"));

  const signer = useSigner();

  const [check, setCheck] = useState<CheckDict | null>(null);
  const [state, setState] = useState<any>(null);
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [evidenceNote, setEvidenceNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [snap, setSnap] = useState<TxSnapshot>({ phase: "idle" });

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [chk, st] = await Promise.all([getCheck(checkId), getChallengeState(checkId)]);
      setCheck(chk);
      setState(st);
    } catch (err: any) {
      setError(err.message);
    }
  }, [checkId]);

  useEffect(() => {
    if (Number.isFinite(checkId)) reload();
  }, [checkId, reload]);

  const contractNow = useContractClock();
  const challengeRemaining = useCountdown(check?.challenge_window_ends_at || 0, contractNow);

  async function submit() {
    setFormError(null);
    if (!signer) {
      setFormError("Sign in first.");
      return;
    }
    if (!/^https:\/\//.test(evidenceUrl)) {
      setFormError("Evidence URL must be HTTPS.");
      return;
    }
    if (!evidenceNote.trim()) {
      setFormError("A short note explaining the evidence is required.");
      return;
    }
    const result = await runTrackedWrite(
      () => submitChallengeEvidence(signer, loanId, checkId, evidenceUrl.trim(), evidenceNote.trim()),
      setSnap
    );
    if (result.phase === "finalized") {
      setEvidenceUrl("");
      setEvidenceNote("");
      await reload();
    }
  }

  if (!Number.isFinite(checkId)) return <ErrorState body="Missing or invalid checkId" />;
  if (error) return <div className="mx-auto max-w-3xl px-4 py-10"><ErrorState body={error} /></div>;
  if (!check || !state) return <div className="mx-auto max-w-3xl px-4 py-10"><LoadingState /></div>;

  const windowOpen = state.window_open && !state.finalized && challengeRemaining > 0;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <p className="font-onchain text-xs text-on-surface-variant">
        Loan #{loanId} · Covenant #{covenantId} · Check #{checkId}
      </p>
      <div className="mt-1 flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-on-surface">Dispute / challenge portal</h1>
        <StatusBadge status={check.status} />
      </div>
      <p className="mt-2 text-sm text-on-surface-variant">
        {windowOpen
          ? <>Challenge window open — <Countdown targetTs={check.challenge_window_ends_at} nowTs={contractNow} /> remaining.</>
          : `Challenge window closed at ${formatTs(check.challenge_window_ends_at)}.`}
      </p>

      <Card className="mt-6">
        <h2 className="text-sm font-semibold text-on-surface">Original pinned source</h2>
        <p className="mt-2 font-onchain text-sm text-on-surface">{check.snapshot_hash}</p>
        <p className="mt-1 text-xs text-on-surface-variant">
          Pinned at {formatTs(check.snapshot_ts)}. This cannot be edited, replaced, or removed — the form below can
          only add further evidence.
        </p>
      </Card>

      {check.challenge_evidence_urls.length > 0 && (
        <Card className="mt-4">
          <h2 className="text-sm font-semibold text-on-surface">Submitted evidence ({check.challenge_evidence_urls.length})</h2>
          <ul className="mt-3 space-y-3">
            {check.challenge_evidence_urls.map((url, i) => (
              <li key={i} className="rounded border border-outline-variant bg-surface-container-lowest p-3">
                <Mono className="break-all text-xs text-on-surface">{url}</Mono>
                <p className="mt-1 text-sm text-on-surface-variant">{check.challenge_evidence_notes[i]}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="mt-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-on-surface">Add evidence</h2>
            <p className="mt-1 text-xs text-on-surface-variant">
              Additive only — there is no way to edit or remove the original source or any prior evidence from this
              form, by design.
            </p>
          </div>
          {windowOpen && (
            <Button
              variant="secondary"
              className="shrink-0"
              onClick={() => {
                setEvidenceUrl("https://docs.genlayer.com/core-concepts/consensus");
                setEvidenceNote(
                  "Independent source showing the current consensus/validator state at the time of this check, submitted for validator re-review."
                );
              }}
            >
              Fill sample data <span className="text-on-surface-variant">(for testing)</span>
            </Button>
          )}
        </div>
        <div className="mt-4 space-y-4">
          <Field label="Evidence URL">
            <Input placeholder="https://…" value={evidenceUrl} onChange={(e) => setEvidenceUrl(e.target.value)} disabled={!windowOpen} />
          </Field>
          <Field label="Note">
            <TextArea
              rows={3}
              placeholder="Explain why this evidence changes the assessment…"
              value={evidenceNote}
              onChange={(e) => setEvidenceNote(e.target.value)}
              disabled={!windowOpen}
            />
          </Field>
          {formError && <ErrorState body={formError} />}
          <TxStatusPanel snap={snap} />
          <Button onClick={submit} disabled={!signer || !windowOpen || snap.phase === "submitted" || snap.phase === "pending" || snap.phase === "finalized"}>
            {snap.phase === "submitted" || snap.phase === "pending" ? "Submitting…" : snap.phase === "finalized" ? "Evidence submitted" : "Submit additional evidence"}
          </Button>
        </div>
      </Card>

      <Button
        href={`/loans/${loanId}/covenants/${covenantId}/check?checkId=${checkId}`}
        variant="ghost"
        className="mt-4"
      >
        Back to check status
      </Button>
    </div>
  );
}
