import { formatGen } from "@/lib/format";

// Collateral Health Gauge — ratio of collateral currently deposited/held
// vs. principal outstanding, driven from real loan ledger fields.
export function CollateralGauge({
  collateralWei,
  principalWei,
  breachTier,
}: {
  collateralWei: number | bigint | string;
  principalWei: number | bigint | string;
  breachTier: number;
}) {
  const collateral = BigInt(collateralWei);
  const principal = BigInt(principalWei);
  // Keep wei arithmetic entirely in BigInt; mixing it with a number throws
  // at runtime and previously crashed the loan detail route.
  const pct = principal > 0n
    ? Math.max(0, Math.min(100, Number((collateral * 10_000n) / principal) / 100))
    : 0;
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
