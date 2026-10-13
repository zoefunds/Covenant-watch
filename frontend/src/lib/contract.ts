"use client";

// Thin, typed wrappers around every public method of contracts/covenant_watch.py.
// Reads use getReadClient(); writes use getWalletClient() and return the
// transaction hash for real lifecycle tracking via waitForTx (see tx.ts).
// Method names/args are taken directly from contracts/covenant_watch.py —
// never invented.

import { ensureGenLayerNetwork, getReadClient, getWalletClient, CONTRACT_ADDRESS } from "./genlayer";
import { GENLAYER_NETWORK } from "./config";

export type SourceType = "ONCHAIN" | "OFFCHAIN";

// Shape expected inside create_loan's `covenants_json` array — matches
// _validate_covenant_definition's accepted keys exactly (raw `threshold`,
// not pre-scaled; the contract itself scales it via _scale()).
export interface CovenantInput {
  source_type: SourceType;
  source_ref: string;
  source_refs?: string[];
  challenge_source_refs?: string[];
  condition_field: string;
  operator: ">=" | "<=" | ">" | "<" | "==";
  threshold: number;
  description: string;
  tier1_interest_step_up_bps: number;
  tier2_seizure_bps: number;
}

// Mirrors VAGUE_CONDITION_FRAGMENTS in contracts/covenant_watch.py so the
// form can reject vague text client-side too, before ever hitting the chain.
export const VAGUE_CONDITION_FRAGMENTS = [
  "financially healthy",
  "good standing",
  "reasonable",
  "appropriate",
  "best efforts",
  "as needed",
  "responsible manner",
  "acceptable",
  "satisfactory",
  "sound judgment",
  "commercially reasonable",
];

export const CHALLENGE_WINDOW_BOUNDS = { min: 5 * 60, max: 7 * 24 * 60 * 60, default: 48 * 60 * 60 };
export const MAX_COVENANTS_PER_LOAN = 8;
export const MATURITY_GRACE_SECONDS = 14 * 24 * 60 * 60;

// Field shapes below mirror _loan_dict/_covenant_dict/_check_dict in
// contracts/covenant_watch.py EXACTLY (status fields are already the
// human-readable string the contract itself emits via LOAN_STATUS_NAMES /
// COVENANT_STATUS_NAMES — never a raw int decoded client-side).
export interface LoanDict {
  id: number;
  base_loan_id: number;
  commitment: string;
  lender: string;
  borrower: string;
  principal_wei: number;
  collateral_wei: number;
  base_interest_bps: number;
  current_interest_bps: number;
  maturity_ts: number;
  drawdown_deadline_ts: number;
  settlement_grace_seconds: number;
  challenge_window_seconds: number;
  covenant_count: number;
  principal_deposited: number;
  principal_claimed: boolean;
  collateral_deposited: number;
  claimable_lender_wei: number;
  claimable_borrower_wei: number;
  repaid_amount_wei: number;
  status: "CREATED" | "ACTIVE" | "BREACH_TIER1" | "BREACH_TIER2" | "DEFAULTED" | "REPAID" | "CANCELLED" | "TIMEOUT_RECLAIMED";
  breach_tier: number;
  created_at: number;
}

export interface CovenantDict {
  id: number;
  loan_id: number;
  loan_covenant_index: number;
  commitment: string;
  source_type: SourceType;
  source_ref: string;
  source_refs: string[];
  challenge_source_refs: string[];
  condition_field: string;
  operator: string;
  // Returned by the contract as a decimal STRING (e.g. "1.050000"), not a
  // number — GenVM's real calldata encoder rejects native Python float,
  // so get_covenant()/get_loan_covenants() return a fixed-point string
  // instead (see _format_scaled in contracts/covenant_watch.py). Parse
  // with Number()/parseFloat() where arithmetic is needed.
  threshold: string;
  description: string;
  tier1_interest_step_up_bps: number;
  tier2_seizure_bps: number;
  confirmed_breach_count: number;
  last_check_id: number;
}

export interface CheckDict {
  id: number;
  loan_id: number;
  covenant_id: number;
  triggered_by: string;
  snapshot_ts: number;
  snapshot_hash: string;
  pinned_source_hash?: string;
  status: "PENDING" | "COMPLIANT" | "BREACH" | "INCONCLUSIVE";
  // Same string-not-number rationale as CovenantDict.threshold above.
  observed_value: string;
  observed_note: string;
  result_source_hash: string;
  evaluated_at: number;
  challenge_window_ends_at: number;
  challenge_count: number;
  challenge_pending: boolean;
  challenge_evidence_urls: string[];
  challenge_evidence_notes: string[];
  finalized: boolean;
}

export const TERMINAL_LOAN_STATUSES = new Set([
  "DEFAULTED",
  "REPAID",
  "CANCELLED",
  "TIMEOUT_RECLAIMED",
]);

async function read<T = any>(functionName: string, args: any[] = []): Promise<T> {
  const client = getReadClient();
  return client.readContract({
    address: CONTRACT_ADDRESS,
    functionName,
    args,
  }) as Promise<T>;
}

// Every write uses the exact EIP-6963 provider selected at connection time.
export interface Signer {
  provider: any;
  address: string;
}

async function write(signer: Signer, functionName: string, args: any[] = [], value: bigint = 0n) {
  await ensureGenLayerNetwork(signer.provider);
  // Account is bound on the client itself (see getWalletClient) so viem
  // normalizes it into a proper Account — never pass the raw address
  // string as a per-call `account` here, see genlayer.ts for why.
  const client = getWalletClient(signer.provider, signer.address);
  await client.connect(GENLAYER_NETWORK);
  return client.writeContract({
    address: CONTRACT_ADDRESS,
    functionName,
    args,
    value,
  });
}

// ---- Views ----
export const getLoan = (loanId: number) => read<LoanDict>("get_loan", [loanId]);
export const getCovenant = (covenantId: number) => read<CovenantDict>("get_covenant", [covenantId]);
export const getLoanCovenants = (loanId: number) => read<CovenantDict[]>("get_loan_covenants", [loanId]);
export const getCheck = (checkId: number) => read<CheckDict>("get_check", [checkId]);
export const getCheckHistory = (loanId: number) => read<CheckDict[]>("get_check_history", [loanId]);
export const getCovenantCheckHistory = (covenantId: number) =>
  read<CheckDict[]>("get_covenant_check_history", [covenantId]);
export const getChallengeState = (checkId: number) => read<any>("get_challenge_state", [checkId]);
export const getLoanCount = () => read<number>("get_loan_count", []);
export const getCurrentTime = () => read<number>("get_current_time", []);
export const canClaimPrincipal = (loanId: number) => read<boolean>("can_claim_principal", [loanId]);
export async function listLiveLoans(): Promise<any[]> {
  const count = Number(await getLoanCount());
  const loans: any[] = [];
  for (let id = 0; id < count; id++) {
    const loan = await getLoan(id);
    if (loan) {
      // Match the backend list shape so the UI can safely use either source.
      loans.push({
        ...loan,
        chain_loan_id: loan.id,
        lender_address: loan.lender,
        borrower_address: loan.borrower,
        interest_bps: loan.current_interest_bps,
      });
    }
  }
  return loans;
}
export const getCooldownRemaining = (loanId: number, covenantId: number, address: string) =>
  read<number>("get_cooldown_remaining", [loanId, covenantId, address]);

// ---- Writes (each takes the connected Signer first) ----
export const createLoan = (
  signer: Signer,
  baseLoanId: number,
  loanCommitment: string,
  borrower: string,
  principalUsdc: bigint,
  collateralWei: bigint,
  baseInterestBps: number,
  maturityTs: number,
  drawdownDeadlineTs: number,
  settlementGraceSeconds: number,
  covenants: CovenantInput[],
  challengeWindowSeconds: number,
) =>
  write(
    signer,
    "create_loan",
    [baseLoanId, loanCommitment, borrower, principalUsdc, collateralWei, baseInterestBps, maturityTs, drawdownDeadlineTs, settlementGraceSeconds, JSON.stringify(covenants), challengeWindowSeconds]
  );

export const activateBaseLoan = (signer: Signer, loanId: number, baseTxHash: string) =>
  write(signer, "activate_base_loan", [loanId, baseTxHash]);

export const triggerCovenantCheck = (signer: Signer, loanId: number, covenantId: number) =>
  write(signer, "trigger_covenant_check", [loanId, covenantId]);

export const submitChallengeEvidence = (
  signer: Signer,
  loanId: number,
  checkId: number,
  evidenceUrl: string,
  evidenceNote: string
) => write(signer, "submit_challenge_evidence", [loanId, checkId, evidenceUrl, evidenceNote]);

export const finalizeCovenantCheck = (signer: Signer, loanId: number, checkId: number) =>
  write(signer, "finalize_covenant_check", [loanId, checkId]);
