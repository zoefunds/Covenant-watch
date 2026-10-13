# Covenant Watch milestone: Base Sepolia USDC and GenLayer adjudication

Completed 13 October 2026.

## Outcome

The milestone separates economic execution from intelligent adjudication. Base Sepolia is the only value layer, and GenLayer StudioNet is used only to decide covenant outcomes. The backend connects the chains through a narrow decision relay, while users authorize every loan and USDC action with their own browser wallet.

## Deployed system

| Component | Address or transaction |
|---|---|
| Base Sepolia escrow | `0x6b806484E938E8Bf5eD65D1841543931240834ef` |
| Base deployment transaction | `0x7240cc53bb05537aee0ced6675a4760d14204bbdd205676e2b1b8c34c44b5d1f` |
| Base owner/deployer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Dedicated Base relayer | `0x35F5ea45122eE7Dd5Ec6aA6aab961E9147e3e9e8` |
| Relayer funding transaction | `0xd2088bc32f7cf7143b0e5f44060fc2e0eacdb55fa58264e50d885b031bfdec34` |
| Circle Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| GenLayer adjudicator | `0xb86d1525014c80F98E7f0C3Be2af60AF3ab761F8` |
| GenLayer deployment transaction | `0x15aeb14989c76229ad0e409cb5affdbafea1aca643eef0113eafd5aecf3a4d9b` |
| Frontend | https://covenant-watch.vercel.app |
| Backend | https://covenant-watch-api.fly.dev |

The GenLayer deployment finalized successfully with five `AGREE` votes. Direct read-only checks showed zero loans on both contracts, and the production API returned `[]` from `/loans`. No live E2E loan was created after redeployment, by request; the current deployment therefore has no claimed transaction-flow proof beyond deployment and read-only verification.

## Base Sepolia work

`contracts/base/CovenantWatchEscrow.sol` now owns all USDC economics:

- lender principal enters through `createLoan` after ERC-20 approval;
- borrower collateral enters through `stakeCollateral` after approval;
- `claimPrincipal` releases principal only after enough unique compliant decisions;
- `repay` pulls the exact principal-plus-interest amount;
- `cancel` and `settleMatured` resolve expired or terminal positions;
- `claimSettlement` uses pull payments for credited balances;
- `applyDecision` accepts only the configured relayer and prevents replay by `(loanId, checkId)`;
- first and second breaches apply interest step-up and partial seizure, while the third produces terminal default.

The contract uses six-decimal USDC amounts, checks-effects-interactions, and a non-reentrancy guard around token movement. Owner and relayer rotation are explicit administrative functions.

## GenLayer work

`contracts/covenant_watch.py` is adjudication-only. `create_loan` records the paired Base loan ID, six-decimal economic terms, immutable source configuration, consequence parameters, and challenge window without receiving value. `activate_base_loan` records the confirmed staking transaction. Checks use validator consensus over independently fetched evidence, challenges are additive, and `finalize_covenant_check` makes a result relayable after the challenge window. `mark_decision_relayed` records the confirmed Base receipt.

Native GEN escrow, repayment, and settlement are not part of the GenLayer contract. An `ACCEPTED` transaction is not treated as complete; application code waits for `FINALIZED` and successful execution.

## Backend work

The FastAPI service remains the non-authoritative index, SIWE session service, and protected URL-preview service. It also has one funded capability: the dedicated Base Sepolia relayer key. The indexer reads finalized GenLayer checks, submits only their mapped decision and immutable consequence values to Base, waits for confirmation, and records the Base hash on GenLayer. It cannot move user funds through origination, staking, draw, repayment, or settlement functions.

Production configuration points to both fresh contracts. The relayer key is stored only as the Fly secret `BASE_RELAYER_PRIVATE_KEY`; the private key is not documented or committed.

## Frontend work

Reown and wagmi were removed. Wallets are discovered directly with EIP-6963, and the user explicitly selects a provider when more than one is installed. The same EIP-1193 provider handles SIWE, Base Sepolia, and GenLayer operations.

Origination now exposes distinct steps for USDC approval, Base principal escrow, and GenLayer registration. The application switches and verifies the network at each boundary. Borrower activation similarly approves and stakes USDC on Base before recording the Base transaction on GenLayer. Loan detail actions use Base for draw, repayment, maturity, and settlement; covenant checks and challenges remain on GenLayer.

The `/loans` route contains no hard-coded verified-loan cards. It displays only data indexed from the configured GenLayer deployment and enriches that data with Base state. A counter-consistency guard prevents origination when the fresh Base and GenLayer loan counters do not match.

## Verification and acceptance status

- Base deployment receipt: confirmed.
- Base constructor configuration and zero loan count: read directly.
- GenLayer deployment receipt: successful and finalized with five agreeing validators.
- GenLayer zero loan count: read directly.
- Fly service: healthy and configured for the fresh address pair.
- Vercel production deployment: `dpl_BG3fddp9AQWHYgTYFpESUZ8fJJ8J`.
- Local Foundry escrow suite: 3 passed, 0 failed.
- Backend pytest suite: 17 passed, 0 failed.
- Frontend ESLint, TypeScript checking, and production build: passed.
- Live paired-chain E2E on these addresses: **not run**; reserved for user acceptance.

The optional live runner remains in `tests/e2e/cross_chain_live.py`, but its historical receipts are intentionally not presented as proof for the current deployments.

## Source comparison

The milestone starts at commit `59098877f02507ee4b57f79a1edfb01aa667f792`. The current comparison is:

https://github.com/zoefunds/Covenant-watch/compare/59098877f02507ee4b57f79a1edfb01aa667f792...main
