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

const sleep = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

// StudioNet's public RPC occasionally returns an HTML gateway page instead of
// JSON. That is a transport outage, not a chain result: keep the UI pending
// and retry it. Deliberately keep this narrow so genuine contract failures
// still reach the user immediately.
function isTransientRpcError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /unexpected token '<'|<!doctype|not valid json|gateway|bad gateway|service unavailable|\b502\b|\b503\b|\b504\b|network error|fetch failed|econnreset|etimedout/i.test(message);
}

async function getTransactionWithRetry(client: any, hash: `0x${string}`): Promise<any> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      return await client.getTransaction({ hash });
    } catch (error) {
      if (!isTransientRpcError(error) || attempt === 5) throw error;
      lastError = error;
      await sleep(1_500 * (attempt + 1));
    }
  }
  throw lastError;
}

async function waitForFinalizedReceipt(client: any, hash: `0x${string}`): Promise<any> {
  let lastError: unknown;
  // Each SDK wait owns a five-minute polling window. A gateway failure often
  // aborts that wait immediately; retry only those failures within the same
  // one-hour finality budget instead of presenting a false terminal failure.
  for (let attempt = 0; attempt < 12; attempt++) {
    try {
      return await client.waitForTransactionReceipt({
        hash,
        status: TransactionStatus.FINALIZED,
        retries: 100,
        interval: 3000,
      });
    } catch (error) {
      if (!isTransientRpcError(error) || attempt === 11) throw error;
      lastError = error;
      await sleep(Math.min(2_000 * (attempt + 1), 15_000));
    }
  }
  throw lastError;
}

function enumName(raw: unknown, names: Record<string, string>): string | undefined {
  if (raw === undefined || raw === null || raw === "") return undefined;
  const value = String(raw);
  return /^\d+$/.test(value) ? names[value] : value;
}

function executionResultOf(transaction: any): string | undefined {
  const explicit = enumName(
    transaction?.txExecutionResultName
      ?? transaction?.txExecutionResult
      ?? transaction?.tx_execution_result,
    executionResultNumberToName as Record<string, string>
  );
  if (explicit) return explicit;

  // StudioNet's FINALIZED receipt represents successful GenVM execution in
  // the leader receipt (execution_result: "SUCCESS"), not necessarily in the
  // SDK's optional txExecutionResult field. Treat the authoritative leader
  // receipt as success immediately so callers can refresh finalized contract
  // state instead of showing a false "unknown execution" error.
  const consensus = transaction?.consensusData ?? transaction?.consensus_data;
  const rawLeader = consensus?.leaderReceipt ?? consensus?.leader_receipt;
  const leader = Array.isArray(rawLeader) ? rawLeader[0] : rawLeader;
  const leaderResult = String(leader?.executionResult ?? leader?.execution_result ?? "").toUpperCase();
  if (["SUCCESS", "FINISHED_WITH_RETURN", "RETURN"].includes(leaderResult)) {
    return ExecutionResult.FINISHED_WITH_RETURN;
  }
  if (["ERROR", "FAILED", "FINISHED_WITH_ERROR", "REVERTED"].includes(leaderResult)) {
    return ExecutionResult.FINISHED_WITH_ERROR;
  }
  return undefined;
}

function executionErrorOf(transaction: any): string | undefined {
  const consensus = transaction?.consensus_data ?? transaction?.consensusData;
  const leader = consensus?.leader_receipt ?? consensus?.leaderReceipt;
  const receipts = Array.isArray(leader) ? leader : leader ? [leader] : [];
  for (const receipt of receipts) {
    const detail = receipt?.genvm_result ?? receipt?.genvmResult ?? receipt?.error;
    if (typeof detail === "string" && detail.trim()) return detail.trim().slice(0, 500);
    if (detail && typeof detail === "object") {
      const message = detail.error_description ?? detail.errorDescription ?? detail.raw_error ?? detail.rawError ?? detail.stderr;
      if (typeof message === "string" && message.trim()) return message.trim().slice(0, 500);
    }
  }
  return undefined;
}

/**
 * A StudioNet transaction can become FINALIZED a few RPC reads before the
 * consensus-data contract exposes txExecutionResult. Poll the transaction
 * itself so that this short indexing delay is not misreported as a revert.
 */
async function waitForExecutionResult(client: any, hash: `0x${string}`, initialReceipt: any) {
  let transaction = initialReceipt;
  let executionResult = executionResultOf(transaction);

  for (let attempt = 0; attempt < 20 && (!executionResult || executionResult === ExecutionResult.NOT_VOTED); attempt++) {
    await sleep(1500);
    transaction = await getTransactionWithRetry(client, hash);
    executionResult = executionResultOf(transaction);
  }

  return { transaction, executionResult };
}

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
    const receipt = await waitForFinalizedReceipt(client, hash);
    // Prefer the SDK's decoded enum name; `status` may be the numeric on-chain
    // enum value (7 for FINALIZED) depending on provider/version.
    const rawStatus = (receipt as any)?.statusName ?? (receipt as any)?.status;
    const statusName = enumName(rawStatus, transactionsStatusNumberToName as Record<string, string>);
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
    const { transaction, executionResult } = await waitForExecutionResult(client, hash, receipt);
    if (executionResult !== ExecutionResult.FINISHED_WITH_RETURN) {
      const executionError = executionErrorOf(transaction);
      const snap: TxSnapshot = {
        phase: "failed",
        hash,
        statusName,
        result: transaction,
        error: executionResult === ExecutionResult.FINISHED_WITH_ERROR
          ? `Transaction finalized, but contract execution reverted. No state was changed.${executionError ? ` GenVM: ${executionError}` : ""}`
          : "Transaction is finalized, but its execution result is not yet available from StudioNet. Refresh to read the finalized contract state; do not resubmit the transaction.",
      };
      onUpdate(snap);
      return snap;
    }
    const snap: TxSnapshot = { phase: "finalized", hash, statusName, result: transaction };
    onUpdate(snap);
    return snap;
  } catch (err: any) {
    const snap: TxSnapshot = { phase: "failed", hash, error: err?.message || String(err) };
    onUpdate(snap);
    return snap;
  }
}

export { DONE_STATUSES, FAILURE_STATUSES };
