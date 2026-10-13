# Base Sepolia payment contract

`CovenantWatchEscrow.sol` is Covenant Watch's only value-bearing contract. It escrows lender principal, stakes borrower collateral, accepts exact repayment, applies finalized adjudication decisions, and exposes pull-based settlement claims. GenLayer never holds funds.

## Current deployment

- Network: Base Sepolia, chain ID `84532`
- Contract: `0x6b806484E938E8Bf5eD65D1841543931240834ef`
- Deployment transaction: `0x7240cc53bb05537aee0ced6675a4760d14204bbdd205676e2b1b8c34c44b5d1f`
- Circle test USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Relayer: `0x35F5ea45122eE7Dd5Ec6aA6aab961E9147e3e9e8`
- Amount units: USDC base units with 6 decimals
- Initial/current documented loan count: `0`

The relayer can only call `applyDecision`; `(loanId, checkId)` replay protection prevents the same adjudication from being applied twice. User wallets call all value-moving lifecycle functions directly.

Build and test locally with `forge build` and `forge test -vv`. See root `DEPLOYMENT.md` for deployment and acceptance procedures. No live E2E loan has been run on the current address.
