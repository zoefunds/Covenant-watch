# Base Sepolia payment contract

`CovenantWatchEscrow.sol` is Covenant Watch's only value-bearing contract. It escrows lender principal, stakes borrower collateral, accepts exact repayment, applies finalized adjudication decisions, and exposes pull-based settlement claims. GenLayer never holds funds.

## Current deployment

- Network: Base Sepolia, chain ID `84532`
- Contract: `0xcCebA6072A607fed1674547B68EF3Fb1b30F867e`
- Deployment transaction: `0xf17e5d27d9451e50a16130e314840a71e2cbc79acb875b086f62f5d9bea45a29`
- Circle test USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Relayer: `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb`
- Amount units: USDC base units with 6 decimals
- Live acceptance loan count: `3`

The relayer can only call `applyDecision`. Every decision also needs an unexpired signature from `decisionSigner`, bound to this Base contract, chain ID, immutable GenLayer contract, loan/check/covenant identity, verdict, and both frozen commitments. `(loanId, checkId)` replay protection prevents the same adjudication from being applied twice. User wallets call all value-moving lifecycle functions directly.

Origination uses `COVENANT_WATCH_LOAN_V3`. In addition to the covenant commitments, the loan commitment contains `COVENANT_WATCH_PENALTY_SCHEDULE_V1`, which Base independently recomputes from the ordered tier-1 and tier-2 arrays. This prevents Base from accepting different in-range economic consequences under a GenLayer-approved commitment.

Build and test locally with `forge build` and `forge test -vv`. See root `DEPLOYMENT.md` for deployment and acceptance procedures.
