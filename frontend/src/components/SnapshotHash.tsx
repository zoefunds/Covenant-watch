import { Mono } from "./ui";
import { formatTs, shortAddr } from "@/lib/format";

// Pinned Snapshot Hash — the exact source hash/url/block the contract
// pinned BEFORE evaluation (trust-boundary requirement #3 in memory.md),
// rendered from the real CheckRecord returned by get_check(). Never
// re-derived or guessed client-side.
export function SnapshotHash({
  sourceRef,
  snapshotHash,
  snapshotTs,
}: {
  sourceRef: string;
  snapshotHash: string;
  snapshotTs: number;
}) {
  return (
    <div className="rounded border border-outline-variant bg-surface-container-lowest p-3">
      <p className="text-xs font-onchain uppercase tracking-wide text-on-surface-variant">Pinned snapshot</p>
      <div className="mt-2 space-y-1.5 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-on-surface-variant">Source:</span>
          <Mono className="break-all text-on-surface">{sourceRef}</Mono>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-on-surface-variant">Hash:</span>
          <Mono className="break-all text-on-surface">{shortAddr(snapshotHash, 10) || "—"}</Mono>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-on-surface-variant">Pinned at:</span>
          <Mono className="text-on-surface">{formatTs(snapshotTs)}</Mono>
        </div>
      </div>
      <p className="mt-2 text-xs text-on-surface-variant">
        This snapshot was written on-chain before validators evaluated the covenant — it cannot be altered after
        the fact.
      </p>
    </div>
  );
}
