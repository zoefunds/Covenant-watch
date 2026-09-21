# Covenant Watch — Project Memory

Living status doc. Update this as work progresses; it is the canonical
source of truth for what's built vs. pending.

## What this project is

An on-chain covenant-monitoring / automatic-penalty lending protocol on
GenLayer. Lenders and borrowers precommit checkable covenants (onchain
state reads or offchain attestation pages) at loan creation; either party
can trigger a check; GenLayer validators independently fetch/read the
pinned source and reach consensus on a structured
COMPLIANT/BREACH/INCONCLUSIVE result; confirmed breaches apply a graduated,
precommitted consequence schedule (interest step-up -> partial seizure ->
full default) after a challenge window closes.

## Architecture decisions (locked, see full spec for rationale)

- Backend: FastAPI + PostgreSQL (SQLAlchemy + Alembic), Fly.io hosting.
- Frontend: Next.js + TypeScript + Tailwind ("Obsidian Assurance" dark
  design system), Vercel hosting, genlayer-js for all chain interaction.
- Auth: wallet SIWE-style signing only, nonce+verify+httpOnly session.
- Consequence model: graduated tiers, all bps precommitted at creation.
- Challenge window: 6h-7d bounded, 48h default, additive-evidence only.
- Collateral: native GEN, ShipBond escrow pattern (see below).
- The user deploys the contract themselves; this project never deploys.

## Trust-boundary design (spec section 7) — where it lives in the contract

All enforced in `contracts/covenant_watch.py`, not just documented:

1. **Covenant terms are immutable post-creation.** `Covenant` dataclass
   fields (source_type/source_ref/operator/threshold) are set once in
   `create_loan()` and never written anywhere else. `submit_challenge_evidence`
   only appends to `CheckRecord.challenge_evidence_urls/notes`.
2. **Vague conditions rejected at creation.** `_validate_covenant_definition`
   scans `condition_field`/`description` against `VAGUE_CONDITION_FRAGMENTS`
   and requires operator to be one of `>=,<=,>,<,==` with a numeric
   threshold — no "vibe check" covenants possible.
3. **Snapshot pinned before evaluation.** `trigger_covenant_check` writes
   the `CheckRecord` (with `snapshot_hash`/`snapshot_ts`) to storage BEFORE
   calling `_run_covenant_evaluation`.
4. **Nondet functions never touch funds.** `_evaluate_onchain` /
   `_evaluate_offchain` / `leader_fn` / `validator_fn` return ONLY the
   structured `{status, observed_value_scaled, observed_note, source_hash}`
   dict. `_send_gen` / `_apply_consequence` are ordinary deterministic
   methods, never called from inside `gl.vm.run_nondet_unsafe`.
5. **Structured equivalence, not strict_eq.** `_covenant_results_agree`
   requires exact status match plus a numeric tolerance
   (`AGREEMENT_TOLERANCE_BPS` = 2%) on `observed_value_scaled` — never a
   format-only or JSON-schema-only check.
6. **INCONCLUSIVE is a real third state.** Unreachable source or
   unparseable/disagreeing LLM output routes to `COVENANT_INCONCLUSIVE`
   explicitly (`_evaluate_offchain`'s fetch-failure branch,
   `_evaluate_onchain`'s except branch, `_parse_offchain_verdict`'s
   unrecognized-status branch forces validator disagreement rather than
   silently guessing) — never defaults to BREACH or COMPLIANT.
7. **Challenge window is additive-only and bounded.** Enforced in
   `submit_challenge_evidence` (append-only lists, re-evaluation reads the
   same pinned `source_ref` + accumulated evidence) and
   `finalize_covenant_check` (refuses before window end or while a
   challenge is pending).

## Escrow / fund-flow design (ShipBond pattern)

- Single choke point: `_send_gen(to_address, amount)` via
  `@gl.evm.contract_interface _Recipient` (empty View/Write) calling
  `.emit_transfer(value=amount)`. Validates non-empty address and
  `amount > 0` via `gl.vm.UserError`.
- Funds enter only through `@gl.public.write.payable` functions reading
  `gl.message.value` — `create_loan` (principal) and `lock_collateral`
  (collateral, exact-match enforced) — never a caller-supplied amount.
- TERMS (`principal_wei`, `collateral_wei`) vs LEDGER
  (`principal_deposited`, `collateral_deposited`, `claimable_lender_wei`,
  `claimable_borrower_wei`) fields are strictly separated on the `Loan`
  dataclass. Every payout path: read ledger into a local -> zero the ledger
  field -> persist -> THEN `_send_gen` (see `claim_principal`,
  `claim_settlement`, and the zero-then-credit pattern inside
  `_apply_consequence`/`repay_loan`).
- Guard `if <ledger> <= 0: raise UserError` precedes every payout.
- Six named exit paths, each independently zero-then-transfer,
  re-deriving amounts from ledger fields (never parameters):
  1. `repay_loan` — compliant finalize (principal+interest to lender,
     remaining collateral to borrower).
  2. `_apply_consequence` tier==1 — interest step-up only, deliberately no
     fund movement (documented choice: tier1 changes future economics, not
     an immediate seizure).
  3. `_apply_consequence` tier==2 — partial collateral seizure
     (precommitted bps split).
  4. `_apply_consequence` tier==3 (or higher) — full seizure, terminal
     DEFAULTED.
  5. `reclaim_collateral_timeout` — counterparty-silent (lender) timeout
     reclaim, `LENDER_SILENCE_GRACE_SECONDS` (14d) after maturity.
  6. `cancel_loan` — refund before both sides committed (only callable
     while loan is still `LOAN_CREATED`, i.e. before `lock_collateral`).
  All final payouts are pull-based via `claim_settlement` /
  `claim_principal`.

## Contract status: DONE and verified

`contracts/covenant_watch.py` (~1315 lines). Verified in this session
(not just trusted from the prior agent's self-report):

- `genvm-lint check contracts/covenant_watch.py --json` → `"ok": true`
  (19 methods, 9 view / 10 write). Only an informational I200 note that a
  newer runner artifact exists — the pinned hash
  `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` is a
  concrete, verified, non-"latest" version and was deliberately kept.
- Re-read the full contract source end-to-end against spec sections 4/7/10
  and the escrow requirements above — all requirements independently
  confirmed present (see trust-boundary and escrow sections above, each
  citing the exact function).

## Direct-mode tests: DONE and verified

`pytest tests/direct/ -v` → **26 passed, 1 skipped** (see reason below).

Fixed three real bugs left mid-write by the prior (rate-limited) agent
session, plus two harness-compatibility issues in `tests/direct/conftest.py`
(documented inline in the file itself, summarized here):

1. **Loader limitation**: `gltest`'s direct-mode SDK enforces a process-wide
   "only one contract class per process" global
   (`genlayer.gl.genvm_contracts.__known_contract__`) that is never reset
   between deploys, so any test deploying two different contract files
   (e.g. the production contract + a helper stand-in) failed immediately.
   Worked around in `conftest.py` by patching
   `gltest.direct.loader.load_contract_class` to clear that global before
   each module load — this only affects the same-process test harness, not
   contract behavior.
2. **LLM mock float-encoding bug**: `gltest.direct.wasi_mock
   ._handle_llm_request` auto-parses a mocked JSON string response into a
   native Python dict before it round-trips through GenVM calldata
   encoding, which has no float type — so any mocked
   `observed_value` with a decimal (1.2, 0.8 — realistic ratio values)
   silently failed to encode and the contract received `None` instead of
   the mocked verdict. Patched in `conftest.py` to keep the mocked response
   as the plain JSON string it already was, which also more faithfully
   matches production (the contract parses raw LLM text itself via
   `_sanitize_json_text`/`json.loads`).
3. **Cross-contract calls unsupported in direct mode**: the harness has no
   `CallContract` dispatch implementation (confirmed via
   `VMContext._gl_call_hook` being unset and `wasi_mock._handle_gl_call`
   falling through to an "Unknown gl_call request type" trace, returning
   `None`). This means `_evaluate_onchain()`'s real
   `gl.get_contract_at(...)` path — deploying a second helper contract and
   reading its view — cannot be exercised in direct mode at all. Rewrote
   the tier1/tier2/tier3/compliant/cooldown/double-claim/reclaim tests to
   drive the same consequence state machine through the OFFCHAIN covenant
   path (mocked web+LLM) instead, since `_apply_consequence()` is identical
   regardless of which source type produced the structured result. Left
   `test_inconclusive_from_unreachable_onchain_source` as an explicit
   `pytest.skip(...)` with a docstring explaining why, pointing at
   `tests/integration/` as the source of truth for that specific path —
   this is a genuine environment/tooling gap, not something to paper over
   with a fake assertion.
4. Two prior-agent test bugs unrelated to the harness: `direct_alice`/
   `direct_bob` fixtures return raw bytes (not an `Address` wrapper with
   `.as_hex`) in this environment because they're resolved before the
   first deploy sets up the SDK's `sys.path` — added a `to_hex()` helper
   used everywhere instead of `.as_hex`. And the original
   `test_reclaim_collateral_on_lender_timeout` used a hardcoded
   maturity_ts of `4_102_444_800` (year ~2100) while only warping 40 days
   forward, which could never reach maturity+grace — fixed to use a
   near-term maturity relative to the VM's current simulated time.

Coverage confirmed passing: compliant flow, all three breach tiers,
INCONCLUSIVE on offchain fetch failure, cooldown rate-limiting (including
that it's per-address-per-covenant and clears after the window),
challenge-window additive-evidence overturning a BREACH, challenge window
close + finalize, cannot-challenge-after-close, double-claim prevention
(principal and settlement), double-finalize prevention, vague-condition
rejection, missing-operator rejection, challenge-window-bounds rejection,
exact-match collateral enforcement, authorization checks (lock/trigger/
cancel), cancel-before-commitment refund, cancel-after-commitment
rejection, lender-timeout reclaim.

## Pending (not completed this session — see "Next steps")

Given the scope of this task (full-stack app + infra + deploy runbooks)
and the time already spent getting the contract/tests to a genuinely
verified state, the following are **not yet built**:

- `tests/integration/` — gltest-based tests against real GenVM/StudioNet
  consensus, including the ONCHAIN cross-contract covenant path that
  direct-mode cannot exercise (see skip reason above), and genuine
  leader/validator disagreement -> INCONCLUSIVE.
- Backend (FastAPI/Postgres/Alembic/indexer/SIWE/Fly config).
- Frontend (Next.js/Tailwind/genlayer-js/Obsidian Assurance design system).
- `DEPLOYMENT.md`.

## Next steps (exact commands)

1. `genlayer-dev:integration-tests` skill — write
   `tests/integration/test_covenant_watch_integration.py` covering at
   minimum: real ONCHAIN covenant check against a deployed helper registry
   contract, and a genuine leader/validator disagreement scenario. Document
   in this file the exact `gltest` invocation the user runs locally against
   their own Studio/GenVM node (no browser faucet available in this
   sandbox).
2. Scaffold backend under `backend/` per the locked architecture: FastAPI
   app, SQLAlchemy models + Alembic migrations for
   loans/covenants/checks/challenges/sessions/nonces/sync_cursor/
   rate_limit_counters, SIWE nonce+verify+session endpoints, indexer worker
   (Postgres as read cache only), SSRF-protected URL-preview endpoint,
   `/healthz`, Dockerfile, docker-compose.yml, `fly.toml`
   (`min_machines_running >= 1`, no `auto_stop_machines`).
3. Scaffold frontend under `frontend/`: Next.js+TS+Tailwind, Obsidian
   Assurance tokens from
   `/Users/macbook/Documents/stitch_dark_theme_project_design/DESIGN.md`,
   genlayer-js wiring (verify current API via the `genlayer-cli` skill or
   docs plugin before writing any `gl.*`/`createClient` code — do not
   guess), pages per the six prototype HTMLs, `NEXT_PUBLIC_CONTRACT_ADDRESS`
   left blank with a comment.
4. Write `DEPLOYMENT.md` with genlayer-cli deploy command, `fly deploy`
   runbook, `vercel --prod` runbook, and the post-deploy verification
   checklist from JUDGE.md's Human Verification Checklist.

## Commit log (meaningful milestones)

- Verified contract lint-clean, fixed and verified all direct-mode tests
  (26 passed / 1 documented skip), added `.gitignore`, wrote this file.

## DEPLOYED CONTRACT ADDRESS (provided by user 2026-09-21)

The user has deployed `contracts/covenant_watch.py` to GenLayer StudioNet
themselves. The canonical deployed address is:

```
0x078485282E589a2cb43F6D3263753402045b7192
```

This MUST be wired into:
- Backend env var `CONTRACT_ADDRESS` (backend `.env` / Fly secrets)
- Frontend env var `NEXT_PUBLIC_CONTRACT_ADDRESS` (frontend `.env.local` / Vercel env)
- `DEPLOYMENT.md`'s "wiring the deployed address" section, as the concrete
  example value (not just a placeholder) once that section exists.

Any in-progress backend/frontend/deployment-doc work should treat this as
the real, live, canonical address for this project — not a placeholder.

## Backend: DONE and verified (this session)

`backend/` is a complete FastAPI + PostgreSQL backend, built per the
locked architecture. Structure: `app/core` (config/logging/sentry),
`app/models` (SQLAlchemy), `app/schemas` (Pydantic), `app/services`
(auth/SSRF-preview/chain client), `app/workers/indexer.py`, `app/api`
(routes), `alembic/` (migrations), plus `Dockerfile`,
`docker-compose.yml`, `fly.toml`, `.env.example`, `README.md`,
`DEPLOYMENT_BACKEND.md`.

### What's verified (actually run, not just written)

- **Migrations**: Python 3.12 venv (genlayer-py 0.16.3 requires >=3.12;
  this machine's default `python3` is 3.14 which breaks pydantic-core's
  Rust build — used `~/.pyenv/versions/3.12.7`). `alembic revision
  --autogenerate` then `alembic upgrade head` ran clean against a real
  **local Homebrew Postgres 16** instance (Docker Desktop's daemon was not
  running in this sandbox, so docker-compose itself was written but not
  itself exercised — see DEPLOYMENT_BACKEND.md for what that means for
  you before you rely on it). All 8 tables created
  (loans/covenants/checks/challenges/sessions/nonces/sync_cursor/
  rate_limit_counters) with FKs, indexes, and non-negative CHECK
  constraints on every money column.
- **Auth round-trip**: ran the live FastAPI app (`uvicorn`) against that
  Postgres and drove the full SIWE flow with an ephemeral throwaway
  eth-account keypair (test-only, ok per working rules): `POST
  /auth/nonce` → sign the returned message → `POST /auth/verify` → signed
  httpOnly/SameSite=strict session cookie → authenticated `GET /auth/me`
  succeeds → replaying the same signature/nonce correctly 401s
  ("nonce already used") → a signature from a *different* key claiming
  the first address correctly 401s ("signature does not match claimed
  address"). Unauthenticated `GET /auth/me` correctly 401s.
- **SSRF preview endpoint**: confirmed `POST /covenants/preview-source`
  blocks `169.254.169.254` (cloud metadata), `localhost`, `file://`
  scheme, and private ranges, while successfully fetching a real public
  URL (`https://example.com`). DNS is resolved and the resolved IP
  checked (not string-matched), on every redirect hop.
- **Indexer against the REAL deployed contract**: set `CONTRACT_ADDRESS`
  to the live StudioNet address above, restarted the backend, and
  confirmed via `/healthz` that the indexer transitioned from
  `waiting_for_contract_address` (with `CONTRACT_ADDRESS` unset) to a
  successful sync pass (`state: idle`, `last_success_at` populated, no
  error) reading `get_loan_count()` → `0` (correct — no loans created on
  it yet; not fabricated). Then unset `CONTRACT_ADDRESS` again before
  leaving the repo in its default deploy-ready state.
- **genlayer-py API discovery** (verified empirically against the
  installed `genlayer-py==0.16.3`, not guessed): `create_client(chain=...,
  account=...)` and `client.read_contract(address, function_name,
  args=[...])`. Important undocumented finding: `read_contract` requires
  *some* local account bound to the client even for pure view/read calls
  — there is no account-less read path in this SDK version. Since this
  backend is read-only against the chain (all writes happen from the
  user's own wallet in the frontend), `app/services/chain_client.py`
  generates a throwaway ephemeral local keypair purely to satisfy that
  requirement; it never holds funds or signs a write.
- **Tests**: `pytest tests/` → 10 passed (SSRF blocklist parametrized
  cases + SIWE message construction). These are pure unit tests with no
  DB dependency, separate from the manual live round-trip above.

### Design notes worth remembering

- Postgres is a read cache, never source of truth — documented in
  `backend/README.md` "Cache vs. live" section and in code comments on
  `chain_client.read_contract_view` / the `Loan`/`Covenant`/`Check`
  models' docstrings.
- `rate_limit_counters` table + slowapi rate limits are explicitly
  documented (README + code comments) as defense-in-depth / UX only — the
  contract's own on-chain cooldown (`get_cooldown_remaining`) is the real
  enforcement boundary and cannot be bypassed via the API.
- Config reload for `CONTRACT_ADDRESS`: supported path is **restart the
  process** (documented choice over hot-reload, see
  `app/workers/indexer.py` docstring and `README.md`) — a stale cached
  contract address silently pointing at the wrong contract is worse than
  a 10s restart.
- One real bug found and fixed during smoke testing: applying `slowapi`'s
  `@limiter.limit(...)` decorator under a module using `from __future__
  import annotations` broke FastAPI's OpenAPI schema generation and body
  parsing (Pydantic model params silently reinterpreted as query params)
  because the decorator's wrapping changes the effective `__globals__`
  used for forward-ref resolution. Fixed by removing the `__future__`
  import from `app/api/auth.py` and `app/api/covenants.py` (the two
  rate-limited route modules) — documented here so it isn't
  reintroduced by accident.

### Pending / not done in this session

- `docker-compose.yml` / `Dockerfile` are written and structurally
  reviewed but **not themselves run** — Docker Desktop's daemon was not
  available in this sandbox (attempted `open -a Docker`, did not come up
  in time). Before relying on it: run `docker compose up --build` once
  Docker is available and confirm the same `/healthz` + migration
  behavior as the manual venv+local-Postgres path above.
- No integration test hits the indexer against a contract that actually
  *has* loans on it yet (the live contract currently has
  `get_loan_count() == 0`) — the upsert logic in
  `app/workers/indexer.py` (`_upsert_loan`/`_upsert_covenant`/
  `_upsert_check`) is implemented against the exact `_loan_dict`/
  `_covenant_dict`/`_check_dict` shapes in `contracts/covenant_watch.py`
  but has not been exercised against a real non-empty loan. Once a loan
  exists on-chain, rerun the indexer and verify `/loans/{id}` returns it
  correctly shaped.
- Frontend (`frontend/`) not started.
- Consolidated repo-root `DEPLOYMENT.md` not written — `backend/
  DEPLOYMENT_BACKEND.md` holds the backend-specific runbook and is meant
  to be folded in later without losing anything.

### Exact local-dev commands

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate   # must be >=3.12
pip install -r requirements-dev.txt
cp .env.example .env   # set SESSION_SECRET; leave CONTRACT_ADDRESS blank
                        # until you deploy, or set it to
                        # 0x078485282E589a2cb43F6D3263753402045b7192
                        # to point at this project's live StudioNet deploy

# point DATABASE_URL in .env at a real local Postgres, e.g.:
#   postgresql+psycopg://<user>@localhost:5432/covenant_watch

alembic upgrade head
uvicorn app.main:app --reload --port 8000
curl localhost:8000/healthz

# or, once Docker is available:
docker compose up --build
```
