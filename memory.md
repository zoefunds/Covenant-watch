# Covenant Watch — Current Operational Record

Last verified: 2026-10-05 (Africa/Lagos)

This file records current state only. Historical addresses, retired hostnames,
superseded failures, and completed TODOs have intentionally been removed. Use
Git history when an older implementation record is needed.

## Production

| Component | Current value |
|---|---|
| GenLayer network | StudioNet |
| Audited contract | `0xcabD9990BdC2B45f22C60b4Ea519041e42c3E980` |
| Deployment transaction | `0x3d217c7937e857e77f31cd9b5a087f2050d4ec40ee7c61b84a2a5c283ef4f374` |
| Frontend | https://covenant-watch.vercel.app |
| Vercel project | `covenant-watch` |
| Backend | https://covenant-watch-api.fly.dev |
| Backend health | https://covenant-watch-api.fly.dev/healthz |
| Fly app | `covenant-watch-api` |
| Fly region | `iad` |

The contract deployment reached `FINALIZED` after three `AGREE` votes reached
quorum; the remaining two validators were `IDLE`. Production frontend deployment `dpl_EL4ZawCqfvU6zhXNWVkeBQcA725v`
was built with the audited address and promoted to the canonical alias. The Fly
backend image `deployment-01M45A1V0MZHRXZQDBFMJD2607` passed its Alembic
release command and rolling health checks. The application uses the same
contract address.

## Contract authority and trust boundaries

- The contract is the sole authority for authorization, escrow accounting,
  lifecycle transitions, deadlines, cooldowns, challenge eligibility,
  covenant outcomes, breach consequences, repayment, and settlement.
- The backend has no funded signer and no contract write/verdict endpoint. It
  cannot alter a covenant, report compliance, move escrow, or finalize a check.
- Frontend wallets submit writes directly through `genlayer-js`.
- OFFCHAIN covenants commit 3–5 HTTPS URLs at origination. URLs and hostnames
  must be unique. Every leader and validator independently fetches every URL;
  callers and the backend cannot supply fetched content.
- A strict majority of the source set must independently produce numeric values
  agreeing within the contract's 2% tolerance. Otherwise the result is
  `INCONCLUSIVE`; ambiguity never becomes an economic penalty.
- The model extracts only a value. The contract deterministically applies the
  immutable operator and threshold to classify `COMPLIANT` or `BREACH`.
- Each check stores the fetched-bundle hash plus bounded per-publisher fetch and
  extraction diagnostics. The full page body is not accepted from a caller.
- Challenge evidence is additive and requires three distinct publisher hosts
  before reevaluation. A challenge result is bound to the original result hash.
- A confirmed breach consequence is applied only after its contract-enforced
  challenge window closes.
- Publisher collusion is the remaining oracle assumption. Validators can prove
  independent retrieval and consensus, not the truthfulness of all publishers.
  Signed attestations or a stronger oracle network would be a separate product
  enhancement and must not introduce backend verdict authority.

## Frontend finality and time behavior

- Write flows explicitly wait for `FINALIZED`, not the SDK's default
  `ACCEPTED` state.
- A finalized receipt is successful only when execution finished with a return;
  a finalized revert or GenVM error remains a UI failure.
- After finality, the frontend immediately rereads finalized contract state.
- Submitted one-shot actions are locally disabled, and successful actions stay
  disabled once refreshed contract state shows they cannot be repeated.
- The principal-claim button remains disabled until the contract's
  `can_claim_principal` view confirms that every covenant has a latest finalized
  `COMPLIANT` check. `claim_principal` independently enforces the same rule.
- Maturity, grace, challenge-window, and cooldown displays use a clock offset
  obtained from `get_current_time`; countdowns update once per second and action
  availability mirrors contract-enforced timestamps.

## Live proof

The production-gate lifecycle was executed on StudioNet against the audited
deployment using three independent publisher pages:

- `https://en.wikipedia.org/wiki/Bitcoin`
- `https://river.com/learn/terms/1/21-million/`
- `https://www.fidelitydigitalassets.com/research-and-insights/understanding-bitcoin-and-ethereum-supply`

Loan `0` completed the payable flow: create loan, lock collateral, trigger an
LLM-backed validator check, claim principal, repay, and claim both
settlement balances. The finalized check reported:

- status: `COMPLIANT`
- observed value: `21000000.000000`
- publisher quorum: `3/3`
- agreeing execution validators observed by the harness: `3`
- terminal loan state: `REPAID`

An earlier attempt against cryptocurrency JSON API endpoints produced a GenVM
host `INTERNAL_ERROR` before any validator round (`NO_MAJORITY`, zero validators).
It did not create a covenant verdict or apply a consequence. Publisher-page
sources completed successfully. The stored `source_diagnostics` field now makes
ordinary fetch failures and inconclusive extractions visible per publisher.

## Verification baseline

- Contract direct tests: 38 passed.
- Backend tests: 17 passed.
- Frontend ESLint: passed.
- Frontend TypeScript (`tsc --noEmit`): passed.
- Frontend Next.js production build: passed with webpack. Optional Reown/Wagmi
  connector-resolution warnings remain non-fatal and all routes were emitted.
- `git diff --check`: passed.
- Backend dependency restored to the pinned `genlayer-py==0.18.0` after live
  tooling temporarily installed an older compatible SDK.

The installed local GLSim still drops payable call values, so payable local
escrow tests skip there. This is not a production gate because the complete
payable and LLM-backed path passed on StudioNet.

## Operational rules

- Keep the contract address identical in Vercel
  `NEXT_PUBLIC_CONTRACT_ADDRESS`, Fly `CONTRACT_ADDRESS`, local env files, and
  documentation.
- Never treat backend cache data or `ACCEPTED` transaction state as final.
- Never add a backend signer or backend-mediated covenant verdict.
- Do not reuse a failed or timed-out write blindly. Resolve its transaction
  status and on-chain state first, then resume by the existing loan/check ID.
- Run the contract, backend, frontend, and live checks described in
  `AUDIT.md` and `DEPLOYMENT.md` before promoting a new contract address.
