import { formatGen } from "@/lib/format";

// Collateral Health Gauge — ratio of collateral currently deposited/held
// vs. principal outstanding, driven from real loan ledger fields.
export function CollateralGauge({
  collateralWei,
  principalWei,
  breachTier,
}: {
  collateralWei: number;
  principalWei: number;
  breachTier: number;
}) {
  const ratio = principalWei > 0 ? collateralWei / principalWei : 0;
  const pct = Math.max(0, Math.min(100, Math.round(ratio * 100)));
  const color = breachTier >= 3 ? "bg-error" : breachTier >= 1 ? "bg-secondary-container" : "bg-tertiary-container";
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-on-surface-variant">
        <span className="font-onchain uppercase tracking-wide">Collateral health</span>
        <span className="font-onchain text-on-surface">{pct}%</span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-surface-container-high">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 font-onchain text-xs text-on-surface-variant">
        {formatGen(collateralWei)} collateral vs {formatGen(principalWei)} principal
      </p>
    </div>
  );
}
