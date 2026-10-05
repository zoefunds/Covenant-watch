"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Field, Input, Select, TextArea, ErrorState } from "@/components/ui";
import { TxStatusPanel } from "@/components/TxStatusPanel";
import { Countdown, useContractClock } from "@/components/Countdown";
import { useWallet } from "@/context/WalletContext";
import { useSigner } from "@/lib/useSigner";
import { previewSource, syncLoans } from "@/lib/api";
import { runTrackedWrite, TxSnapshot } from "@/lib/tx";
import { createLoan, CovenantInput, VAGUE_CONDITION_FRAGMENTS, CHALLENGE_WINDOW_BOUNDS, MAX_COVENANTS_PER_LOAN } from "@/lib/contract";
import { CONTRACT_ADDRESS } from "@/lib/config";
import { genToWei, formatDuration, formatBps } from "@/lib/format";

type DraftCovenant = CovenantInput & { _previewLoading?: boolean; _previewBody?: string; _previewError?: string };

const EMPTY_COVENANT: DraftCovenant = {
  source_type: "OFFCHAIN",
  source_ref: "",
  source_refs: ["", "", ""],
  condition_field: "",
  operator: ">=",
  threshold: 0,
  description: "",
  tier1_interest_step_up_bps: 200,
  tier2_seizure_bps: 2500,
};

function validateCovenant(c: DraftCovenant, idx: number): string | null {
  if (c.source_type === "OFFCHAIN") {
    const sources = c.source_refs ?? [];
    if (sources.length < 3 || sources.some((url) => !/^https:\/\//.test(url))) {
      return `Covenant ${idx + 1}: provide at least three public HTTPS publisher URLs`;
    }
    try {
      const hosts = sources.map((url) => new URL(url).hostname.toLowerCase());
      if (new Set(hosts).size !== hosts.length) {
        return `Covenant ${idx + 1}: each OFFCHAIN source must use a distinct publisher hostname`;
      }
    } catch {
      return `Covenant ${idx + 1}: every OFFCHAIN source must be a valid HTTPS URL`;
    }
  }
  if (c.source_type === "ONCHAIN" && !c.source_ref.trim()) return `Covenant ${idx + 1}: source is required`;
  if (c.source_type === "ONCHAIN" && !/^0x[0-9a-fA-F]{38,40}$/.test(c.source_ref)) {
    return `Covenant ${idx + 1}: ONCHAIN source must be a contract address`;
  }
  if (c.source_type === "ONCHAIN" && c.source_ref.toLowerCase() === CONTRACT_ADDRESS.toLowerCase()) {
    return `Covenant ${idx + 1}: the Covenant Watch contract is not a data source. Use a separate contract that exposes get_${c.condition_field || "<field>"}().`;
  }
  if (!c.condition_field.trim()) return `Covenant ${idx + 1}: condition field is required`;
  if (!c.description.trim()) return `Covenant ${idx + 1}: description is required`;
  const lowerField = c.condition_field.toLowerCase();
  const lowerDesc = c.description.toLowerCase();
  for (const frag of VAGUE_CONDITION_FRAGMENTS) {
    if (lowerField.includes(frag) || lowerDesc.includes(frag)) {
      return `Covenant ${idx + 1}: not independently checkable — contains the vague phrase "${frag}". The contract will reject this too.`;
    }
  }
  if (Number.isNaN(c.threshold)) return `Covenant ${idx + 1}: threshold must be numeric`;
  return null;
}

export default function NewLoanPage() {
  const contractNow = useContractClock();
  const router = useRouter();
  const { sessionAddress } = useWallet();
  const signer = useSigner();

  const [borrower, setBorrower] = useState("");
  const [principalGen, setPrincipalGen] = useState("");
  const [collateralGen, setCollateralGen] = useState("");
  const [interestBps, setInterestBps] = useState(500);
  const [maturityDate, setMaturityDate] = useState("");
  const [challengeWindow, setChallengeWindow] = useState(CHALLENGE_WINDOW_BOUNDS.default);
  const [covenants, setCovenants] = useState<DraftCovenant[]>([{ ...EMPTY_COVENANT }]);
  const [formError, setFormError] = useState<string | null>(null);
  const [snap, setSnap] = useState<TxSnapshot>({ phase: "idle" });

  function updateCovenant(i: number, patch: Partial<DraftCovenant>) {
    setCovenants((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }

  function fillSampleData() {
    setFormError(null);
    // Borrower is a counterparty distinct from the connected wallet, so this
    // is a realistic-format example address, not a fabricated live one.
    setBorrower("0x8f3a2Cc1B4e6D9057F1a1b2C3d4E5f60718293A4");
    setPrincipalGen("1000");
    setCollateralGen("1500");
    setInterestBps(500);
    const inSixWeeks = new Date(Date.now() + 42 * 24 * 60 * 60 * 1000);
    setMaturityDate(inSixWeeks.toISOString().slice(0, 16));
    setChallengeWindow(CHALLENGE_WINDOW_BOUNDS.default);
    setCovenants([
      {
        ...EMPTY_COVENANT,
        source_type: "OFFCHAIN",
        source_refs: [
          "https://en.wikipedia.org/wiki/Bitcoin",
          "https://river.com/learn/terms/1/21-million/",
          "https://www.fidelitydigitalassets.com/research-and-insights/understanding-bitcoin-and-ethereum-supply",
        ],
        condition_field: "max_bitcoin_supply",
        operator: "==",
        threshold: 21000000,
        description: "Independent publishers must corroborate Bitcoin maximum supply as 21,000,000.",
        tier1_interest_step_up_bps: 150,
        tier2_seizure_bps: 3000,
      },
    ]);
  }

  async function previewCovenantUrl(i: number) {
    const c = covenants[i];
    const url = c.source_refs?.[0] ?? "";
    if (c.source_type !== "OFFCHAIN" || !/^https?:\/\//.test(url)) return;
    updateCovenant(i, { _previewLoading: true, _previewError: undefined });
    try {
      const res = await previewSource(url);
      updateCovenant(i, { _previewLoading: false, _previewBody: res.truncated_body.slice(0, 500) });
    } catch (err: any) {
      updateCovenant(i, { _previewLoading: false, _previewError: err.message });
    }
  }

  async function handleSubmit() {
    setFormError(null);
    if (!signer) {
      setFormError("Connect and sign in with a wallet first.");
      return;
    }
    if (!/^0x[0-9a-fA-F]{40}$/.test(borrower)) {
      setFormError("Borrower must be a valid 0x address.");
      return;
    }
    if (!principalGen || Number(principalGen) <= 0) {
      setFormError("Principal must be a positive GEN amount.");
      return;
    }
    if (!collateralGen || Number(collateralGen) <= 0) {
      setFormError("Collateral must be a positive GEN amount.");
      return;
    }
    if (!maturityDate) {
      setFormError("Maturity date is required.");
      return;
    }
    const maturityTs = Math.floor(new Date(maturityDate).getTime() / 1000);
    if (maturityTs <= Math.floor(contractNow)) {
      setFormError("Maturity must be in the future.");
      return;
    }
    if (challengeWindow < CHALLENGE_WINDOW_BOUNDS.min || challengeWindow > CHALLENGE_WINDOW_BOUNDS.max) {
      setFormError(
        `Challenge window must be between ${formatDuration(CHALLENGE_WINDOW_BOUNDS.min)} and ${formatDuration(CHALLENGE_WINDOW_BOUNDS.max)}.`
      );
      return;
    }
    if (covenants.length < 1 || covenants.length > MAX_COVENANTS_PER_LOAN) {
      setFormError(`A loan needs 1..${MAX_COVENANTS_PER_LOAN} covenants.`);
      return;
    }
    for (let i = 0; i < covenants.length; i++) {
      const err = validateCovenant(covenants[i], i);
      if (err) {
        setFormError(err);
        return;
      }
    }

    const cleanCovenants: CovenantInput[] = covenants.map((c) => ({
      source_type: c.source_type,
      source_ref: c.source_ref.trim(),
      source_refs: c.source_type === "OFFCHAIN" ? (c.source_refs ?? []).map((url) => url.trim()) : undefined,
      condition_field: c.condition_field.trim(),
      operator: c.operator,
      threshold: c.threshold,
      description: c.description.trim(),
      tier1_interest_step_up_bps: c.tier1_interest_step_up_bps,
      tier2_seizure_bps: c.tier2_seizure_bps,
    }));

    const result = await runTrackedWrite(
      () =>
        createLoan(
          signer,
          borrower,
          genToWei(collateralGen),
          interestBps,
          maturityTs,
          cleanCovenants,
          challengeWindow,
          genToWei(principalGen)
        ),
      setSnap
    );

    if (result.phase === "finalized") {
      try {
        await syncLoans();
      } catch {
        // The normal backend poll remains the fallback.
      }
      router.push("/loans");
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-on-surface">Originate a loan</h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            Defines principal, checkable covenants, and a graduated consequence schedule. This writes a real
            <code className="mx-1 font-onchain text-xs">create_loan</code> transaction with the principal attached as
            call value.
          </p>
        </div>
        <Button variant="secondary" onClick={fillSampleData} className="shrink-0">
          Fill sample data <span className="text-on-surface-variant">(for testing)</span>
        </Button>
      </div>

      {!sessionAddress && (
        <div className="mt-6 rounded border border-secondary/40 bg-secondary-container/10 p-4 text-sm text-on-surface-variant">
          Connect and sign in with a wallet to originate a loan.
        </div>
      )}

      <div className="mt-8 space-y-6">
        <Card>
          <h2 className="mb-4 text-sm font-semibold text-on-surface">Loan terms</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Borrower address">
              <Input placeholder="0x…" value={borrower} onChange={(e) => setBorrower(e.target.value)} />
            </Field>
            <Field label="Maturity date">
              <Input type="datetime-local" value={maturityDate} onChange={(e) => setMaturityDate(e.target.value)} />
              {maturityDate && Number.isFinite(new Date(maturityDate).getTime()) && (
                <p className="mt-1 text-xs text-on-surface-variant">
                  Time until maturity: <Countdown targetTs={Math.floor(new Date(maturityDate).getTime() / 1000)} nowTs={contractNow} />
                </p>
              )}
            </Field>
            <Field label="Principal (GEN)" hint="Attached as the transaction's call value">
              <Input placeholder="1000" value={principalGen} onChange={(e) => setPrincipalGen(e.target.value)} />
            </Field>
            <Field label="Required collateral (GEN)" hint="Borrower must lock this exact amount">
              <Input placeholder="1500" value={collateralGen} onChange={(e) => setCollateralGen(e.target.value)} />
            </Field>
            <Field label="Base interest (bps)">
              <Input
                type="number"
                value={interestBps}
                onChange={(e) => setInterestBps(Number(e.target.value))}
              />
            </Field>
            <Field
              label={`Challenge window: ${formatDuration(challengeWindow)}`}
              hint={`Bounded ${formatDuration(CHALLENGE_WINDOW_BOUNDS.min)} – ${formatDuration(CHALLENGE_WINDOW_BOUNDS.max)}`}
            >
              <input
                type="range"
                min={CHALLENGE_WINDOW_BOUNDS.min}
                max={CHALLENGE_WINDOW_BOUNDS.max}
                step={3600}
                value={challengeWindow}
                onChange={(e) => setChallengeWindow(Number(e.target.value))}
                className="w-full accent-[#00F0FF]"
              />
            </Field>
          </div>
        </Card>

        {covenants.map((c, i) => (
          <Card key={i}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-on-surface">Covenant {i + 1}</h2>
              {covenants.length > 1 && (
                <button
                  className="text-xs text-error hover:underline"
                  onClick={() => setCovenants((prev) => prev.filter((_, idx) => idx !== i))}
                >
                  Remove
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Source type">
                <Select
                  value={c.source_type}
                  onChange={(e) => updateCovenant(i, { source_type: e.target.value as any })}
                >
                  <option value="OFFCHAIN">OFFCHAIN (URL)</option>
                  <option value="ONCHAIN">ONCHAIN (contract)</option>
                </Select>
              </Field>
              {c.source_type === "OFFCHAIN" ? (
                <div className="sm:col-span-2">
                  <Field
                    label="Independent publisher URLs"
                    hint="At least three distinct HTTPS hostnames. The contract requires a numeric majority before any verdict."
                  >
                    <div className="space-y-2">
                      {(c.source_refs ?? ["", "", ""]).map((url, sourceIndex) => (
                        <Input
                          key={sourceIndex}
                          placeholder={`https://publisher-${sourceIndex + 1}.example/report`}
                          value={url}
                          onChange={(e) => {
                            const next = [...(c.source_refs ?? ["", "", ""] )];
                            next[sourceIndex] = e.target.value;
                            updateCovenant(i, { source_refs: next });
                          }}
                          onBlur={() => sourceIndex === 0 && previewCovenantUrl(i)}
                        />
                      ))}
                    </div>
                  </Field>
                </div>
              ) : (
                <Field label="Source contract address" hint="0x… GenLayer contract">
                  <Input
                    placeholder="0x…"
                    value={c.source_ref}
                    onChange={(e) => updateCovenant(i, { source_ref: e.target.value })}
                  />
                </Field>
              )}
              <Field label="Condition field" hint="Specific, checkable field name — no vague phrasing">
                <Input
                  placeholder="e.g. debt_to_equity_ratio"
                  value={c.condition_field}
                  onChange={(e) => updateCovenant(i, { condition_field: e.target.value })}
                />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Operator">
                  <Select value={c.operator} onChange={(e) => updateCovenant(i, { operator: e.target.value as any })}>
                    {[">=", "<=", ">", "<", "=="].map((op) => (
                      <option key={op} value={op}>
                        {op}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Threshold">
                  <Input
                    type="number"
                    step="any"
                    value={c.threshold}
                    onChange={(e) => updateCovenant(i, { threshold: Number(e.target.value) })}
                  />
                </Field>
              </div>
              <div className="sm:col-span-2">
                <Field label="Description" hint="Specific and checkable — vague terms are rejected by the contract itself">
                  <TextArea
                    rows={2}
                    placeholder="e.g. Reported debt_to_equity_ratio must stay at or below 2.0"
                    value={c.description}
                    onChange={(e) => updateCovenant(i, { description: e.target.value })}
                  />
                </Field>
              </div>
              <Field label="Tier 1: interest step-up (bps)" hint="Applied on first confirmed breach">
                <Input
                  type="number"
                  value={c.tier1_interest_step_up_bps}
                  onChange={(e) => updateCovenant(i, { tier1_interest_step_up_bps: Number(e.target.value) })}
                />
              </Field>
              <Field label="Tier 2: partial seizure (bps of collateral)" hint="Applied on second confirmed breach">
                <Input
                  type="number"
                  value={c.tier2_seizure_bps}
                  onChange={(e) => updateCovenant(i, { tier2_seizure_bps: Number(e.target.value) })}
                />
              </Field>
              <p className="sm:col-span-2 text-xs text-on-surface-variant">
                Tier 3 (full default) is automatic on a third confirmed breach — no additional configuration.
              </p>
            </div>
            {c.source_type === "OFFCHAIN" && c.source_refs?.[0] && (
              <div className="mt-3 rounded border border-outline-variant bg-surface-container-lowest p-3 text-xs">
                {c._previewLoading && <p className="text-on-surface-variant">Fetching live preview…</p>}
                {c._previewError && <p className="text-error">{c._previewError}</p>}
                {c._previewBody && (
                  <>
                    <p className="mb-1 text-on-surface-variant">
                      Live preview (informational only — the contract does its own independent fetch at check time):
                    </p>
                    <p className="max-h-24 overflow-hidden font-onchain text-on-surface-variant">{c._previewBody}</p>
                  </>
                )}
              </div>
            )}
          </Card>
        ))}

        {covenants.length < MAX_COVENANTS_PER_LOAN && (
          <Button variant="secondary" onClick={() => setCovenants((prev) => [...prev, { ...EMPTY_COVENANT }])}>
            + Add covenant
          </Button>
        )}

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-on-surface">Pre-deployment summary</h2>
          <div className="grid grid-cols-2 gap-y-2 text-xs sm:grid-cols-4">
            <div>
              <p className="text-on-surface-variant">Principal</p>
              <p className="font-onchain text-on-surface">{principalGen || "—"} GEN</p>
            </div>
            <div>
              <p className="text-on-surface-variant">Required collateral</p>
              <p className="font-onchain text-primary-container">{collateralGen || "—"} GEN</p>
            </div>
            <div>
              <p className="text-on-surface-variant">Base interest</p>
              <p className="font-onchain text-on-surface">{formatBps(interestBps)}</p>
            </div>
            <div>
              <p className="text-on-surface-variant">Covenants pinned</p>
              <p className="font-onchain text-on-surface">{covenants.length}</p>
            </div>
          </div>
        </Card>

        {formError && <ErrorState title="Fix the form" body={formError} />}
        <TxStatusPanel snap={snap} />

        <Button onClick={handleSubmit} disabled={!signer || snap.phase === "submitted" || snap.phase === "pending" || snap.phase === "finalized"}>
          {snap.phase === "submitted" || snap.phase === "pending" ? "Submitting…" : snap.phase === "finalized" ? "Loan created" : "Create loan"}
        </Button>
        <p className="text-xs text-on-surface-variant">
          After creation, the borrower locks the exact collateral amount via the loan detail page&apos;s Lock Collateral
          action, then draws the principal.
        </p>
      </div>
    </div>
  );
}
