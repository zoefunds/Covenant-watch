// Validator Consensus Split Meter — real n/m validator agreement, read off
// a transaction receipt's consensus data (never fabricated). Pass null
// while the receipt hasn't produced consensus data yet.
export function ConsensusMeter({
  agree,
  total,
}: {
  agree: number | null;
  total: number | null;
}) {
  if (agree === null || total === null || total === 0) {
    return (
      <div className="rounded border border-outline-variant bg-surface-container-lowest p-3">
        <p className="text-xs font-onchain uppercase tracking-wide text-on-surface-variant">Validator consensus</p>
        <p className="mt-1 text-sm text-on-surface-variant">Not yet available — waiting on validator rounds.</p>
      </div>
    );
  }
  const pct = Math.round((agree / total) * 100);
  return (
    <div className="rounded border border-outline-variant bg-surface-container-lowest p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-onchain uppercase tracking-wide text-on-surface-variant">Validator consensus</p>
        <span className="font-onchain text-sm text-on-surface">
          {agree}/{total} agree
        </span>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-container-high">
        <div
          className="h-full rounded-full bg-primary-container transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
