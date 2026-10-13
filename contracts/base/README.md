# Base Sepolia payment contract

`CovenantWatchEscrow.sol` is Covenant Watch's only value-bearing contract. It
escrows the lender's USDC principal, stakes the borrower's USDC collateral,
accepts repayment, and exposes pull-based settlement claims. GenLayer never
holds funds: the relayer can only submit finalized adjudication results through
`applyDecision`, with `(loanId, checkId)` replay protection.

- Network: Base Sepolia (`84532`)
- USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Amounts: USDC base units (6 decimals)

Compile with `forge build`. Deployment and verified addresses are recorded in
the root `DEPLOYMENT.md` and `milestone.md`.
