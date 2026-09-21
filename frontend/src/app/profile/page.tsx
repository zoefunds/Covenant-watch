"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useWallet } from "@/context/WalletContext";
import { listLoans } from "@/lib/api";
import { Card, EmptyState, ErrorState, LoadingState, Mono } from "@/components/ui";
import { StatusBadge } from "@/components/StatusBadge";
import { formatGen, shortAddr } from "@/lib/format";
import { CONTRACT_ADDRESS } from "@/lib/config";

export default function ProfilePage() {
  const { sessionAddress, address } = useWallet();
  const [loans, setLoans] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionAddress) return;
    (async () => {
      try {
        const [asLender, asBorrower] = await Promise.all([
          listLoans({ lender: sessionAddress }),
          listLoans({ borrower: sessionAddress }),
        ]);
        const byId = new Map<number, any>();
        [...asLender, ...asBorrower].forEach((l) => byId.set(l.chain_loan_id, l));
        setLoans([...byId.values()]);
      } catch (err: any) {
        setError(err.message);
      }
    })();
  }, [sessionAddress]);

  if (!sessionAddress) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <h1 className="text-2xl font-semibold text-on-surface">Profile</h1>
        <div className="mt-6 rounded border border-secondary/40 bg-secondary-container/10 p-4 text-sm text-on-surface-variant">
          {address
            ? "Wallet connected but not signed in — click Sign in to authenticate this session."
            : "Connect a wallet to view your profile."}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl font-semibold text-on-surface">Profile</h1>

      <Card className="mt-6">
        <p className="text-xs text-on-surface-variant">Authenticated session</p>
        <Mono className="mt-1 block break-all text-sm text-on-surface">{sessionAddress}</Mono>
        <p className="mt-3 text-xs text-on-surface-variant">Contract</p>
        <Mono className="mt-1 block break-all text-sm text-on-surface">{CONTRACT_ADDRESS}</Mono>
      </Card>

      <h2 className="mb-3 mt-8 text-sm font-semibold text-on-surface">Your loans</h2>
      {loans === null && !error && <LoadingState />}
      {error && <ErrorState body={error} />}
      {loans && loans.length === 0 && <EmptyState title="No loans involve this address yet" />}
      {loans && loans.length > 0 && (
        <div className="space-y-2">
          {loans.map((loan) => {
            const role = loan.lender_address?.toLowerCase() === sessionAddress.toLowerCase() ? "Lender" : "Borrower";
            return (
              <Link key={loan.chain_loan_id} href={`/loans/${loan.chain_loan_id}`}>
                <Card className="flex items-center justify-between transition-colors hover:border-primary-container/50">
                  <div>
                    <p className="text-sm text-on-surface">
                      Loan #{loan.chain_loan_id} · {role} · {formatGen(loan.principal_wei)}
                    </p>
                    <p className="mt-1 font-onchain text-xs text-on-surface-variant">
                      Counterparty {shortAddr(role === "Lender" ? loan.borrower_address : loan.lender_address)}
                    </p>
                  </div>
                  <StatusBadge status={loan.status} />
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
