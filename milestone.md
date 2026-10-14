# Covenant Watch milestone: Base Sepolia USDC and GenLayer adjudication

Completed 14 October 2026.

## Outcome

The milestone separates economic execution from intelligent adjudication. Base Sepolia is the only value layer, and GenLayer StudioNet is used only to decide covenant outcomes. The backend connects the chains through a narrow decision relay, while users authorize every loan and USDC action with their own browser wallet.

## Deployed system

| Component | Address or transaction |
|---|---|
| Base Sepolia escrow | `0xbF8F70Db480d003Dd6c5629c50b1f9Bf3Adc9E9b` |
| Base deployment transaction | `0x1690edbcf6b5a519ac5c574235579e88a966185f3596251dffc33691b6e9df68` |
| Base owner/deployer and dedicated relayer | `0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A` |
| Decision signer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Circle Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| GenLayer adjudicator | `0x1b4BA5Fe8894648E4B90d80f2DA5d53880CcfD7b` |
| GenLayer deployment transaction | `0x9698a8fa9f6db79cbcda2a0986243d4b60f0f993003049864bdccf7f0aa0634a` |
| Frontend | https://covenant-watch.vercel.app |
| Backend | https://covenant-watch-api.fly.dev |

The GenLayer deployment finalized successfully with five `AGREE` votes. The live acceptance run created three paired loans and the production API indexes all three.

## Base Sepolia work

`contracts/base/CovenantWatchEscrow.sol` now owns all USDC economics:

- lender principal enters through `createLoan` after ERC-20 approval;
- borrower collateral enters through `stakeCollateral` after approval;
- `claimPrincipal` releases principal only after enough unique compliant decisions;
- `repay` pulls the exact principal-plus-interest amount;
- `cancel` and `settleMatured` resolve expired or terminal positions;
- `claimSettlement` uses pull payments for credited balances;
- `applyDecision` accepts only the configured relayer, verifies a separate signer attestation bound to the Base contract, chain, GenLayer contract, loan/check/covenant identity, decision, commitments, and deadline, and prevents replay by `(loanId, checkId)`;
- first and second breaches apply interest step-up and partial seizure, while the third produces terminal default.

The contract uses six-decimal USDC amounts, checks-effects-interactions, and a non-reentrancy guard around token movement. Owner and relayer rotation are explicit administrative functions.

## GenLayer work

`contracts/covenant_watch.py` is adjudication-only. `create_loan` records the paired Base loan ID, six-decimal economic terms, immutable source configuration, consequence parameters, and challenge window without receiving value. `activate_base_loan` records the confirmed staking transaction. Checks use validator consensus over independently fetched evidence, challenges are additive, and `finalize_covenant_check` makes a result relayable after the challenge window. `mark_decision_relayed` records the confirmed Base receipt.

Native GEN escrow, repayment, and settlement are not part of the GenLayer contract. An `ACCEPTED` transaction is not treated as complete; application code waits for `FINALIZED` and successful execution.

## Backend work

The FastAPI service remains the non-authoritative index, SIWE session service, and protected URL-preview service. It holds separate Base relayer and decision-attestation credentials. The indexer reads finalized GenLayer checks, signs a domain-bound decision, submits the authenticated decision to Base, waits for confirmation, and records the Base hash on GenLayer. It cannot move user funds through origination, staking, draw, repayment, or settlement functions.

Production configuration points to both remediation contracts. Credentials are stored only as Fly secrets (`BASE_RELAYER_PRIVATE_KEY` and `DECISION_SIGNER_PRIVATE_KEY`); private keys are not documented or committed.

## Frontend work

Reown and wagmi were removed. Wallets are discovered directly with EIP-6963, and the user explicitly selects a provider when more than one is installed. The same EIP-1193 provider handles SIWE, Base Sepolia, and GenLayer operations.

Origination now exposes distinct steps for USDC approval, Base principal escrow, and GenLayer registration. The application switches and verifies the network at each boundary. Borrower activation similarly approves and stakes USDC on Base before recording the Base transaction on GenLayer. Loan detail actions use Base for draw, repayment, maturity, and settlement; covenant checks and challenges remain on GenLayer.

The `/loans` route contains no hard-coded verified-loan cards. It displays only data indexed from the configured GenLayer deployment and enriches that data with Base state. A counter-consistency guard prevents origination when the fresh Base and GenLayer loan counters do not match.

## Verification and acceptance status

- Base deployment receipt: confirmed.
- Base constructor configuration and live loan state: read directly.
- GenLayer deployment receipt: successful and finalized with five agreeing validators.
- GenLayer paired loan state: read directly.
- Fly service: healthy and configured for the fresh address pair.
- Vercel production deployment: `dpl_2GwcpoH84BXSm3ZJqwr6c2u8b3Mj`.
- Local Foundry security suite: 10 passed, 0 failed.
- Backend/direct suite: 29 passed, 0 failed.
- Frontend ESLint, TypeScript checking, and production build: passed.
- Live paired-chain acceptance: completed with separate lender `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` and borrower `0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A` wallets.

## Live acceptance evidence

See the checked-in [acceptance evidence record](./acceptance-evidence.md) for
explorer links, scenario outcomes, and the verification commands.

The checked-in evidence artifact [`acceptance-evidence.json`](./acceptance-evidence.json) records every receipt, GenVM success, validator vote, state readback, and USDC balance delta. It covers:

- Loan 0: USDC principal escrow, collateral staking, finalized 3/3-source compliant adjudication, forged relay rejection/recovery, borrower draw, exact repayment, lender settlement withdrawal, and borrower collateral withdrawal. Final Base status: `REPAID`.
- Loan 1: three distinct covenant checks, three preauthorized challenge publishers, finalized breach decisions, tier-1/2/3 progression, replay/commitment protections, and lender default withdrawal. Final Base status: `DEFAULTED`, interest `650` bps, escrow balance `0`.
- Loan 2: principal and collateral escrow without draw, maturity plus settlement grace, permissionless settlement, lender principal withdrawal, and borrower collateral withdrawal. Final Base status: `TIMEOUT_RECLAIMED`.

Representative Base receipts include loan-0 escrow `0x8530e9eb2abc8db89025d265808c9834e203c0294d81fc0a3507958f62447198`, breach relays `0xee8ddc93b9e68bc3209a81869063e11fa1732fce6621c25a162a91ad2fc8e4af`, `0xa330e98f1b388f72f22345de300c27b96ac151219e4d2ac7931043f4a3c39a84`, `0x2d53b2c45bde943089c8d07cd7ce6f7a1eb6ee08cceb30eafcaf4f0cd9c89dd2`, and maturity settlement `0xd81a6db9de4dd975a582da1179f45bc6f47f83b714cd25c4b22e1145e8f613e7`. GenLayer finalized transaction hashes and validator votes are retained in the same artifact.

The acceptance runner is `tests/e2e/security_acceptance.py`; it uses no committed private keys and never writes keys to the evidence file.

## Source comparison

The last awarded baseline is commit `e054b6fc629be61f365d6aa83601a3dabc8033ca`. The current comparison is:

https://github.com/zoefunds/Covenant-watch/compare/e054b6fc629be61f365d6aa83601a3dabc8033ca...main
