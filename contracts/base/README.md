# Base Sepolia payment contract

`CovenantWatchEscrow.sol` is Covenant Watch's only value-bearing contract. It escrows lender principal, stakes borrower collateral, accepts exact repayment, applies finalized adjudication decisions, and exposes pull-based settlement claims. GenLayer never holds funds.

## Current deployment

- Network: Base Sepolia, chain ID `84532`
- Contract: `0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2`
- Deployment transaction: `0x3ffd97e520394dc4577420b3df987711bb857f8a305e7868fc6674075dfd8dfb`
- Circle test USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Relayer: `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb`
- Amount units: USDC base units with 6 decimals
- Live acceptance loan count: `3`

The relayer can only call `applyDecision`; `(loanId, checkId)` replay protection prevents the same adjudication from being applied twice. User wallets call all value-moving lifecycle functions directly.

Build and test locally with `forge build` and `forge test -vv`. See root `DEPLOYMENT.md` for deployment and acceptance procedures.
