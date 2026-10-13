# Covenant Watch milestone: Base Sepolia USDC and GenLayer adjudication

Completed 13 October 2026.

## Outcome

The milestone separates economic execution from intelligent adjudication. Base Sepolia is the only value layer, and GenLayer StudioNet is used only to decide covenant outcomes. The backend connects the chains through a narrow decision relay, while users authorize every loan and USDC action with their own browser wallet.

## Deployed system

| Component | Address or transaction |
|---|---|
| Base Sepolia escrow | `0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2` |
| Base deployment transaction | `0x3ffd97e520394dc4577420b3df987711bb857f8a305e7868fc6674075dfd8dfb` |
| Base owner/deployer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Dedicated Base relayer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Relayer funding transaction | `0xd2088bc32f7cf7143b0e5f44060fc2e0eacdb55fa58264e50d885b031bfdec34` |
| Circle Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| GenLayer adjudicator | `0x1EC71Df45C68F9F52A155DbBC8def172B00819C4` |
| GenLayer deployment transaction | `0x375f98f42157f8e3cf941074036f2d26cc140c3fae02b3a1233d630fbca60ffa` |
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
- `applyDecision` accepts only the configured relayer and prevents replay by `(loanId, checkId)`;
- first and second breaches apply interest step-up and partial seizure, while the third produces terminal default.

The contract uses six-decimal USDC amounts, checks-effects-interactions, and a non-reentrancy guard around token movement. Owner and relayer rotation are explicit administrative functions.

## GenLayer work

`contracts/covenant_watch.py` is adjudication-only. `create_loan` records the paired Base loan ID, six-decimal economic terms, immutable source configuration, consequence parameters, and challenge window without receiving value. `activate_base_loan` records the confirmed staking transaction. Checks use validator consensus over independently fetched evidence, challenges are additive, and `finalize_covenant_check` makes a result relayable after the challenge window. `mark_decision_relayed` records the confirmed Base receipt.

Native GEN escrow, repayment, and settlement are not part of the GenLayer contract. An `ACCEPTED` transaction is not treated as complete; application code waits for `FINALIZED` and successful execution.

## Backend work

The FastAPI service remains the non-authoritative index, SIWE session service, and protected URL-preview service. It also has one funded capability: the dedicated Base Sepolia relayer key. The indexer reads finalized GenLayer checks, submits only their mapped decision and immutable consequence values to Base, waits for confirmation, and records the Base hash on GenLayer. It cannot move user funds through origination, staking, draw, repayment, or settlement functions.

Production configuration points to both remediation contracts. The relayer key is stored only as the Fly secret `BASE_RELAYER_PRIVATE_KEY`; the private key is not documented or committed.

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
- Vercel production deployment: `dpl_DGMWNZPc8iaYzZa1cDNuyQuaZcqK`.
- Local Foundry security suite: 9 passed, 0 failed.
- Backend/direct suite: 28 passed, 0 failed.
- Frontend ESLint, TypeScript checking, and production build: passed.
- Live paired-chain acceptance: completed with separate lender `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` and borrower `0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A` wallets.

## Live acceptance evidence

See the checked-in [acceptance evidence record](./acceptance-evidence.md) for
explorer links, scenario outcomes, and the verification commands.

The evidence artifact `/private/tmp/covenant-watch-security-acceptance.json` records every receipt, GenVM success, validator votes, state readback, and USDC balance delta. It covers:

- Loan 0: USDC principal escrow, collateral staking, finalized 3/3-source compliant adjudication, forged relay rejection/recovery, borrower draw, exact repayment, lender settlement withdrawal, and borrower collateral withdrawal. Final Base status: `REPAID`.
- Loan 1: three distinct covenant checks, three preauthorized challenge publishers, finalized breach decisions, tier-1/2/3 progression, replay/commitment protections, and lender default withdrawal. Final Base status: `DEFAULTED`, interest `650` bps, escrow balance `0`.
- Loan 2: principal and collateral escrow without draw, maturity plus settlement grace, permissionless settlement, lender principal withdrawal, and borrower collateral withdrawal. Final Base status: `TIMEOUT_RECLAIMED`.

Representative Base receipts include escrow `0x9c27776d9062b0e039f4ac5eebe5d8098f5296926b76ed1b7d50c9e9321b46cd`, breach relays `0xf7a985632aa2326ff61f9a492963da36e85e1379877627b591b9322c5598adb4`, `0x690afb38f3f1f1f05297321a83526b0d53aba9a87b12c031beb79b00b82f2a3d`, `0xfefc590a690870760a5322cee5a354c9a9b484bd38bb154edd61cd4a94fe0758`, and maturity settlement `0xbef16721ee4e0b24b149e4a65b9aa2a5e13de59cad03aa02405c055b8faaac83`. GenLayer finalized transaction hashes and validator votes are retained in the same artifact.

The acceptance runner is `tests/e2e/security_acceptance.py`; it uses no committed private keys and never writes keys to the evidence file.

## Source comparison

The last awarded baseline is commit `e054b6fc629be61f365d6aa83601a3dabc8033ca`. The current comparison is:

https://github.com/zoefunds/Covenant-watch/compare/e054b6fc629be61f365d6aa83601a3dabc8033ca...main
