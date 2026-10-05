"use client";

// Real transaction lifecycle tracking — no client-side setTimeout ever
// stands in for status. Every write call in this app returns a GenLayer tx
// hash, which we poll with the SDK's own waitForTransactionReceipt /
// getTransaction against real chain state.

import { getReadClient } from "./genlayer";
import {
  ExecutionResult,
  TransactionStatus,
  executionResultNumberToName,
  transactionsStatusNumberToName,
} from "genlayer-js/types";

export type TxPhase = "idle" | "submitted" | "pending" | "finalized" | "failed";

export interface TxSnapshot {
  phase: TxPhase;
  hash?: `0x${string}`;
  statusName?: string;
  error?: string;
  result?: any;
}

const FAILURE_STATUSES = new Set(["CANCELED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT", "UNDETERMINED"]);
const DONE_STATUSES = new Set(["FINALIZED"]);

/**
 * Drives a write call through to a real terminal state, invoking onUpdate
 * with each intermediate phase so the UI can render submitted -> pending ->
 * finalized/failed against genuine SDK-reported status, never a guess.
 */
export async function runTrackedWrite(
  writeCall: () => Promise<`0x${string}` | any>,
  onUpdate: (snap: TxSnapshot) => void
): Promise<TxSnapshot> {
  onUpdate({ phase: "submitted" });
  let hash: any;
  try {
    const res = await writeCall();
    hash = typeof res === "string" ? res : res?.hash ?? res?.tx_hash ?? res;
  } catch (err: any) {
    const snap: TxSnapshot = { phase: "failed", error: err?.message || String(err) };
    onUpdate(snap);
    return snap;
  }

  onUpdate({ phase: "pending", hash });

  const client = getReadClient();
  try {
    // The SDK defaults to ACCEPTED, which is still appealable. Contract state
    // must not drive UI updates until the transaction is irreversibly final.
    const receipt = await client.waitForTransactionReceipt({
      hash,
      status: TransactionStatus.FINALIZED,
      // Finality can substantially lag acceptance on an appealable
      // intelligent-contract transaction. Keep polling for up to one hour.
      retries: 1200,
      interval: 3000,
    });
    // Prefer the SDK's decoded enum name; `status` may be the numeric on-chain
    // enum value (7 for FINALIZED) depending on provider/version.
    const rawStatus = (receipt as any)?.statusName ?? (receipt as any)?.status;
    const statusName = typeof rawStatus === "number" || /^\d+$/.test(String(rawStatus))
      ? transactionsStatusNumberToName[String(rawStatus) as keyof typeof transactionsStatusNumberToName]
      : rawStatus;
    if (statusName && FAILURE_STATUSES.has(statusName)) {
      const snap: TxSnapshot = { phase: "failed", hash, statusName, error: `Transaction ended in ${statusName}` };
      onUpdate(snap);
      return snap;
    }
    if (statusName !== TransactionStatus.FINALIZED) {
      const snap: TxSnapshot = {
        phase: "failed",
        hash,
        statusName,
        error: `Expected FINALIZED but received ${statusName || "an unknown status"}`,
      };
      onUpdate(snap);
      return snap;
    }
    const rawExecutionResult = (receipt as any)?.txExecutionResultName ?? (receipt as any)?.txExecutionResult;
    const executionResult = typeof rawExecutionResult === "number" || /^\d+$/.test(String(rawExecutionResult))
      ? executionResultNumberToName[String(rawExecutionResult) as keyof typeof executionResultNumberToName]
      : rawExecutionResult;
    if (executionResult !== ExecutionResult.FINISHED_WITH_RETURN) {
      const snap: TxSnapshot = {
        phase: "failed",
        hash,
        statusName,
        result: receipt,
        error: executionResult === ExecutionResult.FINISHED_WITH_ERROR
          ? "Transaction finalized, but contract execution reverted. No state was changed."
          : `Transaction finalized without a successful execution result (${executionResult || "unknown"}).`,
      };
      onUpdate(snap);
      return snap;
    }
    const snap: TxSnapshot = { phase: "finalized", hash, statusName, result: receipt };
    onUpdate(snap);
    return snap;
  } catch (err: any) {
    const snap: TxSnapshot = { phase: "failed", hash, error: err?.message || String(err) };
    onUpdate(snap);
    return snap;
  }
}

export { DONE_STATUSES, FAILURE_STATUSES };
