"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listLoans, getLoanChecksCached, getCheckChallengesCached } from "@/lib/api";
import { Card, EmptyState, ErrorState, LoadingState } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { formatTs } from "@/lib/format";

export default function HistoryPage() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const loans = await listLoans();
        const perLoan = await Promise.all(
          loans.map(async (loan: any) => {
            const checks = await getLoanChecksCached(loan.chain_loan_id).catch(() => []);
            const withChallenges = await Promise.all(
              checks.map(async (c: any) => ({
                ...c,
                loan,
                challenges: await getCheckChallengesCached(c.chain_check_id).catch(() => []),
              }))
            );
            return withChallenges;
          })
        );
        const flat = perLoan.flat().sort((a, b) => new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime());
        setRows(flat);
      } catch (err: any) {
        setError(err.message);
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl font-semibold text-on-surface">History</h1>
      <p className="mt-1 text-sm text-on-surface-variant">
        Full check / challenge / settlement history across all loans, from the backend read cache.
      </p>

      <div className="mt-6">
        {rows === null && !error && <LoadingState label="Loading history…" />}
        {error && <ErrorState body={error} />}
        {rows && rows.length === 0 && <EmptyState title="No checks have been triggered yet" />}
        {rows && rows.length > 0 && (
          <div className="space-y-3">
            {rows.map((row) => (
              <Link key={row.chain_check_id} href={`/loans/${row.loan.chain_loan_id}/covenants/${row.chain_covenant_id}/check?checkId=${row.chain_check_id}`}>
                <Card className="transition-colors hover:border-primary-container/50">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm text-on-surface">
                        Loan #{row.loan.chain_loan_id} · Covenant #{row.chain_covenant_id} · Check #{row.chain_check_id}
                      </p>
                      <p className="mt-1 font-onchain text-xs text-on-surface-variant">{formatTs(new Date(row.triggered_at).getTime() / 1000)}</p>
                    </div>
                    <StatusBadge status={row.status} />
                  </div>
                  {row.challenges.length > 0 && (
                    <p className="mt-2 text-xs text-on-surface-variant">{row.challenges.length} challenge evidence submission(s)</p>
                  )}
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
