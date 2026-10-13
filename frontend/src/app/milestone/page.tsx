import data from "@/data/milestoneScenarios.json";
import { Card, Mono } from "@/components/ui";
import { formatUsdc, shortAddr } from "@/lib/format";

const statusNames = ["Created", "Active", "Tier 1", "Tier 2", "Defaulted", "Repaid", "Cancelled", "Timeout reclaimed"];

export default function MilestonePage() {
  return <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
    <p className="font-onchain text-xs uppercase tracking-widest text-primary-container">Verified milestone</p>
    <h1 className="mt-2 text-3xl font-semibold text-on-surface">Base Sepolia USDC payment evidence</h1>
    <p className="mt-3 max-w-3xl text-sm text-on-surface-variant">
      These are confirmed transactions from the live escrow—not placeholders. GenLayer adjudicates covenant evidence;
      Base Sepolia exclusively handles principal, collateral staking, consequences, repayment, and claims.
    </p>
    <Card className="mt-6 grid gap-3 text-sm sm:grid-cols-3">
      <div><p className="text-xs text-on-surface-variant">Escrow</p><Mono>{shortAddr(data.escrow, 8)}</Mono></div>
      <div><p className="text-xs text-on-surface-variant">USDC</p><Mono>{shortAddr(data.usdc, 8)}</Mono></div>
      <div><p className="text-xs text-on-surface-variant">Evidence captured</p><Mono>{new Date(data.runAt).toLocaleString()}</Mono></div>
    </Card>
    <div className="mt-6 grid gap-4 lg:grid-cols-3">
      {data.scenarios.map((item) => <Card key={item.scenario}>
        <p className="font-onchain text-xs text-primary-container">Scenario {item.scenario} · Loan #{item.loanId}</p>
        <h2 className="mt-2 text-lg font-semibold text-on-surface">{item.title}</h2>
        <p className="mt-2 text-sm text-on-surface-variant">{item.summary}</p>
        <dl className="mt-4 space-y-2 text-xs">
          <div className="flex justify-between gap-3"><dt>Status</dt><dd>{statusNames[item.finalState.status]}</dd></div>
          <div className="flex justify-between gap-3"><dt>Principal</dt><dd>{formatUsdc(item.finalState.principal)}</dd></div>
          <div className="flex justify-between gap-3"><dt>Collateral remaining</dt><dd>{formatUsdc(item.finalState.collateralEscrowed)}</dd></div>
          <div className="flex justify-between gap-3"><dt>Breach tier</dt><dd>{item.finalState.breachTier}</dd></div>
          <div className="flex justify-between gap-3"><dt>Current interest</dt><dd>{(item.finalState.currentInterestBps / 100).toFixed(2)}%</dd></div>
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(item.transactions).flatMap(([event, hashes]) => (hashes as string[]).map((hash: string, i: number) =>
            <a key={`${event}-${hash}`} href={`https://sepolia.basescan.org/tx/${hash.startsWith("0x") ? hash : `0x${hash}`}`} target="_blank" rel="noreferrer" className="rounded border border-outline/30 px-2 py-1 font-onchain text-[10px] text-primary-container hover:border-primary-container">
              {event}{hashes.length > 1 ? ` ${i + 1}` : ""}
            </a>
          ))}
        </div>
      </Card>)}
    </div>
  </div>;
}
