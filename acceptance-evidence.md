# Live remediation acceptance evidence

Run date: 13 October 2026 (Base Sepolia and GenLayer StudioNet)

The run used separate wallets:

- lender/relayer: `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb`
- borrower: `0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A`
- USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Base escrow: `0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2`
- GenLayer adjudicator: `0x1EC71Df45C68F9F52A155DbBC8def172B00819C4`

The machine-readable artifact was generated at
`/private/tmp/covenant-watch-security-acceptance.json`. It contains the active
run's receipt status/block data, validator vote lists, contract tuple
readbacks, and USDC balance snapshots. Loan 0 was resumed from its already
confirmed onchain state and is identified as such in the artifact; its live
GenLayer state is also recorded in the deployment readback.

## Scenario 1 — compliant draw and repayment

Loan `0` was paired with commitment
`0x40558e08bc2faa33c622be92e5e3403b683581763a1703984e13786d3b9ec99d`. The
Base escrow received `1,000,000` USDC and the borrower staked `1,500,000` USDC.
GenLayer read the three pinned publishers as `COMPLIANT` at
`21,000,000.000000`, with validator consensus and a finalized check. The run
rejected a forged relay commitment, then accepted the authentic relay. The
borrower drew principal, repaid `1,050,000` USDC, the lender claimed repayment,
and the borrower claimed collateral. Final Base status: `REPAID`; all escrow
balances: zero.

## Scenario 2 — challenge and three-tier breach

Loan `1` used three distinct covenant commitments. Base receipts prove the
principal and collateral movements, followed by three relays:

- [relay 1](https://sepolia.basescan.org/tx/0xf7a985632aa2326ff61f9a492963da36e85e1379877627b591b9322c5598adb4)
- [relay 2](https://sepolia.basescan.org/tx/0x690afb38f3f1f1f05297321a83526b0d53aba9a87b12c031beb79b00b82f2a3d)
- [relay 3](https://sepolia.basescan.org/tx/0xfefc590a690870760a5322cee5a354c9a9b484bd38bb154edd61cd4a94fe0758)

Each check independently corroborated the breach from three publishers. Three
preauthorized challenge URLs were submitted to the first check; the original
source commitment remained authoritative and the finding stayed `BREACH`.
Final Base state was `DEFAULTED`, breach tier `3`, current interest `650` bps,
and escrow balance `0` after the lender withdrawal.

## Scenario 3 — maturity settlement

Loan `2` received principal and collateral but no draw. After maturity plus its
60-second settlement grace, anyone called `settleMatured`. The lender withdrew
the undrawn `1,000,000` USDC principal and the borrower withdrew the full
`1,500,000` USDC collateral. Final Base status: `TIMEOUT_RECLAIMED`; escrow
balance: zero.

## GenLayer execution

The GenLayer deployment finalized with five agreeing validators. Scenario 2
produced finalized `create_loan`, `activate_base_loan`, three check triggers,
three challenge submissions, three finalizations, and three
`mark_decision_relayed` transactions. Scenario 3 produced finalized creation
and activation transactions. The artifact records each transaction hash and
its validator votes.

## Local regression gates

- Foundry: 9 passed, including distinct-covenant compliance, post-deadline
  draw rejection, forged/excessive relay rejection, pairing mismatch, replay,
  failed-relay recovery, repayment, and maturity settlement.
- Backend/direct tests: 28 passed.
- Frontend ESLint, TypeScript, and production build: passed.
