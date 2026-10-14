# Base Sepolia payment contract

`CovenantWatchEscrow.sol` is Covenant Watch's only value-bearing contract. It escrows lender principal, stakes borrower collateral, accepts exact repayment, applies finalized adjudication decisions, and exposes pull-based settlement claims. GenLayer never holds funds.

## Current deployment

- Network: Base Sepolia, chain ID `84532`
- Contract: `0xbF8F70Db480d003Dd6c5629c50b1f9Bf3Adc9E9b`
- Deployment transaction: `0x1690edbcf6b5a519ac5c574235579e88a966185f3596251dffc33691b6e9df68`
- Circle test USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Relayer: `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb`
- Amount units: USDC base units with 6 decimals
- Live acceptance loan count: `3`

The relayer can only call `applyDecision`. Every decision also needs an unexpired signature from `decisionSigner`, bound to this Base contract, chain ID, immutable GenLayer contract, loan/check/covenant identity, verdict, and both frozen commitments. `(loanId, checkId)` replay protection prevents the same adjudication from being applied twice. User wallets call all value-moving lifecycle functions directly.

Build and test locally with `forge build` and `forge test -vv`. See root `DEPLOYMENT.md` for deployment and acceptance procedures.
