# Covenant Watch security review

Last updated: 13 October 2026.

## Current trust boundary

- Base Sepolia contract `0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2` is the sole authority for USDC custody, draw eligibility, repayment, breach consequences, maturity, and settlement.
- GenLayer contract `0x1EC71Df45C68F9F52A155DbBC8def172B00819C4` is the authority for covenant definitions, evidence evaluation, challenges, and finalized adjudication. It does not custody value.
- Browser wallets directly authorize loan creation, collateral staking, principal draw, repayment, and claims. The backend cannot initiate those user actions.
- The backend holds a dedicated Base relayer key. Its authority is restricted by the Base contract to `applyDecision`; it cannot transfer arbitrary user USDC. This key remains a sensitive production secret and should be rotated if exposed.
- API cache data is eventually consistent and non-authoritative. Contract reads and contract-enforced preconditions remain the final safety boundary.

## Economic contract controls

- Base uses Circle test USDC at `0x036CbD53842c5426634e7929541eC2318f3dCF7e` and six-decimal base units.
- ERC-20 transfers occur only through explicit escrow, stake, repay, and claim paths.
- Token-moving functions use a non-reentrancy guard; settlement credits are zeroed before transfer.
- Principal draw requires collateral and the configured number of unique compliant decisions.
- Decision submissions are authorized by `relayer` and replay-protected by `(loanId, checkId)`.
- Consequences progress across the loan: interest step-up, partial collateral seizure, then terminal default.
- Exact repayment prevents partial-payment ambiguity. Permissionless maturity settlement resolves both undrawn and drawn-unpaid cases.
- The owner can rotate the relayer and transfer ownership. Compromise of the owner can therefore replace the relayer; operational custody of the owner key is a material trust assumption.

## Adjudication controls

- Covenant sources and economic consequence parameters are fixed at creation.
- Off-chain covenants require multiple distinct HTTPS publisher hosts. Validators fetch sources independently and compare structured status, observed value, and source hash.
- A strict publisher majority must corroborate the observed value within the configured tolerance. Missing, ambiguous, or disagreeing evidence yields `INCONCLUSIVE` instead of a penalty.
- Challenge evidence is additive and cannot replace the original source set. Finalization is blocked until the challenge window closes.
- A decision is eligible for relay only after GenLayer finality. `ACCEPTED` alone is insufficient.

## Wallet and cross-chain controls

- The frontend uses direct EIP-6963 discovery and retains the exact provider selected by the user. Reown and wagmi are not part of the runtime.
- Connection and SIWE authentication are separate. Account changes invalidate a mismatched authenticated session.
- Each Base or GenLayer write switches the selected wallet and then verifies the resulting chain before submission.
- Origination compares Base and GenLayer counters before creating the paired loan. A mismatch stops the flow instead of silently pairing unrelated IDs.
- The cross-chain operation is not atomic. A Base creation can confirm before GenLayer registration fails. The UI preserves confirmed transaction hashes and identifies the failed stage so recovery must use existing chain state rather than blindly creating another Base loan.

## Backend controls

- SIWE nonces are single-use and expire; authenticated endpoints rely on signed httpOnly cookies rather than request-body addresses.
- URL preview rejects private, loopback, link-local, reserved, and metadata destinations across redirects. Preview output does not become a validator verdict.
- Indexing uses process and PostgreSQL advisory locks. RPC usage is coordinated through Redis and bounded by the configured hourly budget.
- Relay processing checks finalized indexed results and checks Base replay state before submission. A transaction receipt failure is surfaced instead of recorded as success.

## Current verification status

- Remediation Base deployment transaction: `0x3ffd97e520394dc4577420b3df987711bb857f8a305e7868fc6674075dfd8dfb`.
- Remediation GenLayer deployment transaction: `0x375f98f42157f8e3cf941074036f2d26cc140c3fae02b3a1233d630fbca60ffa`.
- GenLayer deployment: finalized, successful, five agreeing validators.
- Acceptance counters: three paired loans on both chains.
- Production API list after acceptance: three live indexed loans.
- Local Foundry escrow suite: 3 passed, 0 failed.
- Backend pytest suite: 17 passed, 0 failed.
- Frontend ESLint, TypeScript checking, and Next.js production build: passed.
- Live acceptance completed on the remediation pair using separate lender and borrower wallets. It covered Base approvals, principal escrow, collateral staking, finalized GenLayer checks, forged relay rejection and recovery, three-covenant breach progression, challenge evidence, default withdrawal, repayment/settlement, and undrawn maturity settlement. Evidence was written to `/private/tmp/covenant-watch-security-acceptance.json`.

## Residual risks

- Cross-chain state is coordinated operationally rather than by an atomic bridge. Recovery procedures and counter consistency are important.
- The backend relayer and Base owner are privileged roles. Contract restrictions reduce relayer scope, but secure key storage and rotation remain necessary.
- Publisher collusion and incorrect public information are external oracle risks. Multi-source consensus reduces but cannot eliminate them.
- LLM extraction is probabilistic. Validator agreement and fail-closed `INCONCLUSIVE` handling reduce the chance that ambiguity becomes an economic penalty.
- Testnet USDC and StudioNet are not production assets or production-final networks. A mainnet launch requires a new security review, deployment, monitoring, and acceptance test record.
