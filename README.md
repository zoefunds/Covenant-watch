# Covenant Watch

> "Write the promise into the loan. Let the public record decide if it was broken."

Covenant Watch is an onchain covenant-monitoring and automatic-penalty
protocol for GEN-denominated loans, built on [GenLayer](https://genlayer.com)
Intelligent Contracts. Lenders and borrowers precommit checkable loan
covenants at origination; either party can trigger an independent,
validator-consensus-based compliance check at any time; confirmed breaches
apply a graduated, precommitted penalty schedule automatically. No party
self-reports compliance, and no party can unilaterally decide a breach
occurred — the same GenLayer validator set that secures the chain reaches
consensus on what a public source actually says.

## Why this exists

Covenant-lite and covenant-heavy loans alike depend today on trusted
self-reporting: a borrower (or their auditor) says "reserve ratio is still
above 1.05," and the lender either takes their word for it or pays for
expensive off-chain verification after the fact. Covenant Watch replaces
that trust relationship with a neutral, automated inspection: GenLayer's
non-deterministic execution (`gl.vm.run_nondet_unsafe`) lets multiple
validators independently read an onchain source or fetch every URL in a
creation-time-pinned set of independent publishers. The contract requires a
publisher majority and validator consensus, rather than any single party's
say-so.

## The core trust-boundary loop

```
 LOAN + PRECOMMITTED COVENANTS (source + condition + consequence)
        |
 LOCKED COLLATERAL
        |
 CHECK TRIGGER  (pins source-set identity BEFORE evaluation)
        |
 INDEPENDENT VALIDATOR INSPECTION  (gl.vm.run_nondet_unsafe)
        |
 EQUIVALENCE ON STRUCTURED PER-COVENANT RESULT
        |        (custom validator function — never strict_eq or a
        |         format/JSON-schema-only check)
        |
 DETERMINISTIC CONSEQUENCE APPLICATION  (separate, fund-moving code path,
        |        never invoked from inside the nondet block)
        |
 CHALLENGE WINDOW  (additive evidence only — the pinned source itself is
        |        never replaced)
        v
 FINALIZED / IRREVERSIBLE
```

Every step in that loop is enforced in `contracts/covenant_watch.py` itself,
not just documented convention:

- A covenant's `source_type` / source set / `operator` / `threshold` are
  fixed at `create_loan()` time. No function anywhere lets a party change
  them later.
- Vague, non-checkable covenant text (`"good standing"`, `"commercially
  reasonable"`, etc.) is rejected at creation time — every covenant must
  resolve to a specific field, a comparable operator, and a numeric
  threshold.
- `trigger_covenant_check()` writes an immutable snapshot (source hash +
  consensus-agreed timestamp) to storage **before** the non-deterministic
  evaluation runs.
- OFFCHAIN covenants require 3–5 unique HTTPS URLs on distinct hostnames.
  Every leader and validator independently fetches the full pinned set; no
  backend response body or caller-supplied verdict enters evaluation.
- A strict source majority must report values within a 2% numeric tolerance.
  One malicious, unavailable, or ambiguous publisher cannot decide the result.
- Agreement is judged on a **structured** result
  (`{status, observed_value, source_hash}`) with an explicit numeric
  tolerance, never on raw text or bit-exact equality.
- Disagreement beyond tolerance, or an unreachable source, resolves to an
  explicit `INCONCLUSIVE` status — never a default `BREACH` or `COMPLIANT`.
- The non-deterministic functions never touch a ledger field or move funds.
  Fund movement lives exclusively in deterministic methods (`_send_gen`,
  `_apply_consequence`) that are never called from inside a nondet block.
- `submit_challenge_evidence()` only **appends** evidence — it never rewrites
  the pinned source set. Reevaluation requires three distinct evidence hosts.
- `finalize_covenant_check()` refuses to apply an irreversible consequence
  until the challenge window has closed with no challenge pending.

## Escrow design: the ShipBond pattern

All GEN leaves the contract through exactly one function,
`_send_gen(to_address, amount)`, which wraps a single
`@gl.evm.contract_interface` recipient call
(`.emit_transfer(value=amount)`). Every payout path follows the same
**guard → zero the ledger field → persist → then transfer** ordering, so a
repeated or duplicated call always finds the balance already at zero and can
never double-spend:

- `claim_principal` / `claim_settlement` are pull-based withdrawals of a
  `claimable_*_wei` ledger field.
- `TERMS` fields (`principal_wei`, `collateral_wei`) are immutable once set;
  only the separate `LEDGER` fields (`principal_deposited`,
  `collateral_deposited`, `claimable_lender_wei`, `claimable_borrower_wei`)
  are ever mutated, and only through this pattern.
- Six named exit paths — compliant repayment, tier-1 interest step-up
  (no fund movement), tier-2 partial seizure, tier-3 full seizure/default,
  deterministic maturity settlement, and pre-collateral cancellation — each
  independently re-derive the amount to move from ledger state, never from
  a caller-supplied parameter.

## Live deployment

| Component | URL / value |
|---|---|
| Frontend | https://covenant-watch.vercel.app |
| Backend API | https://covenant-watch-api.fly.dev |
| Backend health | https://covenant-watch-api.fly.dev/healthz |
| Contract address | `0x5c3Fe893aaaa9C0416F76812c3903Cf4AfA528A7` |
| Network | GenLayer StudioNet |
| Explorer | https://explorer-studio.genlayer.com/ |

The verified production-gate run finalized loan `2` with a `COMPLIANT`
result at `21000000.000000`, 3/3 independent publishers, three agreeing
execution validators, repayment, and both settlement claims. See
[`AUDIT.md`](./AUDIT.md) for findings and proof, [`DEPLOYMENT.md`](./DEPLOYMENT.md) for the full deploy runbook
(contract, backend, frontend, Postgres, and a post-deploy verification
checklist), and [`memory.md`](./memory.md) for the project's build history
and design decisions.

## Repository structure

```
contracts/covenant_watch.py   The Intelligent Contract — the entire trust
                               boundary and loan/covenant/escrow logic.
backend/                      FastAPI + PostgreSQL + Redis read-cache API,
                               indexer, and SIWE auth service. See
                               backend/README.md.
frontend/                     Next.js + TypeScript + Tailwind app — every
                               loan/covenant write goes directly to the
                               chain via genlayer-js, never through the
                               backend. See frontend/README.md.
tests/direct/                 Fast, mocked-web/LLM unit tests against the
                               contract (gltest direct mode).
tests/integration/            Real (non-mocked) tests — real HTTP fetch,
                               real LLM calls, real cross-contract reads —
                               against a live GenLayer network.
DEPLOYMENT.md                 Full deploy runbook (contract, backend,
                               frontend, Postgres, verification checklist).
memory.md                     Current production and verification record;
                               historical state belongs in Git history.
```

## Tech stack

- **Contract**: GenLayer Intelligent Contract, Python/GenVM
  (`py-genlayer`), pinned runner
  `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`.
- **Backend**: FastAPI, PostgreSQL (SQLAlchemy + Alembic), Redis (Upstash,
  for a shared GenLayer RPC hourly budget and distributed rate limiting),
  deployed on Fly.io.
- **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind v4,
  `genlayer-js` for all chain reads/writes, Reown (WalletConnect) AppKit
  for wallet connection, deployed on Vercel.

## Quickstart (local development)

Clone the repo, then bring up each piece:

### 1. Contract tests (no deployment needed)

```bash
# Fast, mocked-web/LLM tests
pip install -r requirements-dev.txt   # or your existing genlayer-test env
gltest tests/direct/ -v

# Real (non-mocked) tests against a live GenLayer network — see
# tests/integration/ and DEPLOYMENT.md for exact commands and network
# options (studionet is preferred; a local glsim network is also usable
# with your own LLM provider key)
gltest tests/integration/ -v -s --network studionet
```

### 2. Backend

```bash
cd backend
cp .env.example .env
# edit .env: set SESSION_SECRET; point DATABASE_URL at a local Postgres;
# CONTRACT_ADDRESS can stay blank, or point at the live deployment above

python3.12 -m venv .venv && source .venv/bin/activate   # requires >=3.12
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
curl localhost:8000/healthz

# or, with Docker:
docker compose up --build
```

See [`backend/README.md`](./backend/README.md) for the cache-vs-live
pattern, the auth model, and the Redis-backed RPC budget design.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
# .env.local's defaults already point at the live deployed contract
# (0x5c3Fe893aaaa9C0416F76812c3903Cf4AfA528A7, studionet) and a working
# Reown project id for wallet connection

npm run dev      # requires Node >=20.9
npm run build    # production build
npm run lint
```

See [`frontend/README.md`](./frontend/README.md) for the pages, the wallet
connection model, and what's actually been verified.

## Deploying your own contract instance

This project never deploys or holds credentials on your behalf — you run
`genlayer deploy` yourself from your own authenticated GenLayer session,
then wire the resulting address into `backend/.env`'s `CONTRACT_ADDRESS`
and `frontend/.env.local`'s `NEXT_PUBLIC_CONTRACT_ADDRESS`. Full steps,
including a schema/smoke-test verification sequence, are in
[`DEPLOYMENT.md`](./DEPLOYMENT.md).

## License

No LICENSE file is currently present in this repository. Until one is
added, no license terms are granted for reuse beyond what's implied by the
repository's visibility on GitHub.
