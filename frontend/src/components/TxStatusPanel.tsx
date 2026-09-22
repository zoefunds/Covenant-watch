import { TxSnapshot } from "@/lib/tx";
import { Mono } from "./ui";
import { GENLAYER_EXPLORER_URL } from "@/lib/config";

const STEPS: { phase: TxSnapshot["phase"]; label: string }[] = [
  { phase: "submitted", label: "Submitted" },
  { phase: "pending", label: "Pending consensus" },
  { phase: "finalized", label: "Finalized" },
];

export function TxStatusPanel({ snap }: { snap: TxSnapshot }) {
  if (snap.phase === "idle") return null;
  const currentIdx = STEPS.findIndex((s) => s.phase === snap.phase);
  return (
    <div className="rounded border border-outline-variant bg-surface-container-lowest p-3">
      <div className="flex items-center gap-3">
        {STEPS.map((step, i) => {
          const reached = snap.phase === "failed" ? i <= currentIdx : i <= currentIdx;
          const active = step.phase === snap.phase;
          return (
            <div key={step.phase} className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  snap.phase === "failed" && i === currentIdx
                    ? "bg-error"
                    : reached
                    ? "bg-primary-container"
                    : "bg-surface-container-highest"
                } ${active ? "animate-pulse" : ""}`}
              />
              <span className={`text-xs ${reached ? "text-on-surface" : "text-on-surface-variant"}`}>{step.label}</span>
              {i < STEPS.length - 1 && <span className="h-px w-4 bg-outline-variant" />}
            </div>
          );
        })}
      </div>
      {snap.hash && (
        <p className="mt-2 text-xs text-on-surface-variant">
          Tx hash: <Mono className="break-all text-on-surface">{snap.hash}</Mono>{" "}
          <a
            href={`${GENLAYER_EXPLORER_URL.replace(/\/$/, "")}/tx/${snap.hash}`}
            target="_blank"
            rel="noreferrer"
            className="text-primary-container underline"
          >
            view in explorer
          </a>
        </p>
      )}
      {snap.statusName && <p className="mt-1 text-xs text-on-surface-variant">SDK status: {snap.statusName}</p>}
      {snap.phase === "failed" && <p className="mt-2 text-sm text-error">{snap.error}</p>}
      {snap.phase === "finalized" && <p className="mt-2 text-sm text-tertiary-container">Transaction finalized.</p>}
    </div>
  );
}
