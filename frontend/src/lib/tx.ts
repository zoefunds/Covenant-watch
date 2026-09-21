"use client";

// Real transaction lifecycle tracking — no client-side setTimeout ever
// stands in for status. Every write call in this app returns a GenLayer tx
// hash, which we poll with the SDK's own waitForTransactionReceipt /
// getTransaction against real chain state.

import { getReadClient } from "./genlayer";

export type TxPhase = "idle" | "submitted" | "pending" | "finalized" | "failed";

export interface TxSnapshot {
  phase: TxPhase;
  hash?: `0x${string}`;
  statusName?: string;
  error?: string;
  result?: any;
}

const FAILURE_STATUSES = new Set(["CANCELED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT", "UNDETERMINED"]);
const DONE_STATUSES = new Set(["FINALIZED", "ACCEPTED"]);

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
    const receipt = await client.waitForTransactionReceipt({ hash, retries: 40, interval: 3000 });
    const statusName = (receipt as any)?.status ?? (receipt as any)?.statusName;
    if (statusName && FAILURE_STATUSES.has(statusName)) {
      const snap: TxSnapshot = { phase: "failed", hash, statusName, error: `Transaction ended in ${statusName}` };
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
