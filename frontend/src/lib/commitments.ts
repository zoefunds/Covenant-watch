import { concatHex, numberToHex, sha256, stringToHex, type Hex } from "viem";
import type { CovenantInput } from "./contract";

const u = (value: number | bigint, size: number) => numberToHex(BigInt(value), { size });
const text = (value: string): Hex => {
  const body = stringToHex(value);
  return concatHex([u((body.length - 2) / 2, 4), body]);
};

export function normalizedCovenant(covenant: CovenantInput) {
  const sourceRef = covenant.source_type === "OFFCHAIN"
    ? JSON.stringify(covenant.source_refs ?? [])
    : covenant.source_ref;
  const challengeSourceRef = covenant.source_type === "OFFCHAIN"
    ? JSON.stringify(covenant.challenge_source_refs ?? [])
    : "[]";
  return { ...covenant, source_ref: sourceRef, challenge_source_ref: challengeSourceRef };
}

export function covenantCommitment(index: number, covenant: CovenantInput): Hex {
  const c = normalizedCovenant(covenant);
  const thresholdScaled = BigInt(Math.round(c.threshold * 1_000_000));
  return sha256(concatHex([
    stringToHex("COVENANT_WATCH_COVENANT_V2"), u(index, 4),
    text(c.source_type), text(c.source_ref), text(c.challenge_source_ref),
    text(c.condition_field), text(c.operator), text(c.description),
    numberToHex(thresholdScaled, { size: 32, signed: true }),
    u(c.tier1_interest_step_up_bps, 4), u(c.tier2_seizure_bps, 4),
  ]));
}

export function loanCommitment(args: {
  baseLoanId: number; lender: string; borrower: string; principal: bigint;
  collateral: bigint; interestBps: number; maturity: number;
  drawdownDeadline: number; settlementGrace: number; covenantCommitments: Hex[];
  tier1StepBps: number[]; tier2SeizureBps: number[];
}): Hex {
  if (args.tier1StepBps.length !== args.covenantCommitments.length || args.tier2SeizureBps.length !== args.covenantCommitments.length) {
    throw new Error("Penalty schedule must match the covenant count.");
  }
  const penaltySchedule = sha256(concatHex([
    stringToHex("COVENANT_WATCH_PENALTY_SCHEDULE_V1"), u(args.covenantCommitments.length, 2),
    ...args.tier1StepBps.flatMap((step, index) => [u(step, 4), u(args.tier2SeizureBps[index], 4)]),
  ]));
  return sha256(concatHex([
    stringToHex("COVENANT_WATCH_LOAN_V3"), u(args.baseLoanId, 32),
    args.lender as Hex, args.borrower as Hex, u(args.principal, 32), u(args.collateral, 32),
    u(args.interestBps, 4), u(args.maturity, 8), u(args.drawdownDeadline, 8),
    u(args.settlementGrace, 4), u(args.covenantCommitments.length, 2),
    ...args.covenantCommitments, penaltySchedule,
  ]));
}
