// Precision status badges per the Obsidian Assurance design system.
// INCONCLUSIVE gets a distinct, non-alarming slate/neutral treatment — it
// is deliberately NOT styled as an error or a success.

const STYLES: Record<string, string> = {
  COMPLIANT: "bg-tertiary-container/15 text-tertiary-container border-tertiary-container/40",
  BREACH: "bg-error-container/20 text-error text-[--color-error] border-error/50",
  BREACH_TIER1: "bg-error-container/20 text-error border-error/50",
  BREACH_TIER2: "bg-error-container/30 text-error border-error/60",
  DEFAULTED: "bg-error-container/40 text-error border-error/70",
  INCONCLUSIVE: "bg-surface-container-high text-on-surface-variant border-outline-variant",
  PENDING: "bg-secondary-container/15 text-secondary border-secondary/40",
  CHALLENGE_ACTIVE: "bg-secondary-container/25 text-secondary border-secondary/50",
  CREATED: "bg-surface-container-high text-on-surface-variant border-outline-variant",
  ACTIVE: "bg-primary-container/15 text-primary-container border-primary-container/40",
  REPAID: "bg-tertiary-container/15 text-tertiary-container border-tertiary-container/40",
  CANCELLED: "bg-surface-container-high text-on-surface-variant border-outline-variant",
  TIMEOUT_RECLAIMED: "bg-surface-container-high text-on-surface-variant border-outline-variant",
};

export function StatusBadge({ status, className = "" }: { status: string; className?: string }) {
  const cls = STYLES[status] || STYLES.PENDING;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-onchain text-[11px] font-medium uppercase tracking-wide ${cls} ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      {status.replace(/_/g, " ")}
    </span>
  );
}
