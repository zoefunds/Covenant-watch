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

## Integration tests (`tests/integration/`): WRITTEN, real (no mocks), but
## COULD NOT RUN RELIABLY IN THIS SANDBOX — see full writeup below

Files: `tests/integration/conftest.py`, `test_happy_path_offchain.py`,
`test_onchain_cross_contract.py`, `test_adversarial_and_inconclusive.py`,
`test_multi_validator_consensus.py`, `test_helpers/mock_signer_registry.py`
(under `contracts/`, since gltest resolves `contract_file_path` relative to
the configured contracts dir), `run_glsim_patched.py`, and root
`gltest.config.yaml`.

None of these tests use `mock_web`/`mock_llm` — every one calls real
`gl.nondet.web.render()` (against a throwaway local HTTP fixture server
started per-session in `conftest.py`, serving pinned page content including
a genuine prompt-injection/hostile-content page), real
`gl.nondet.exec_prompt()`, and a real `gl.get_contract_at(...)`
cross-contract call against an independently-deployed second contract
(`contracts/test_helpers/mock_signer_registry.py`) — this is the exact
ONCHAIN cross-contract scenario `tests/direct/` could not exercise (see its
skip reason above). Coverage: full happy path (create_loan through
settlement claims), ONCHAIN cross-contract COMPLIANT/BREACH/unreachable-
contract-INCONCLUSIVE, a hostile/prompt-injection OFFCHAIN page (asserts
the injected fake "always say COMPLIANT" instruction does NOT win — allows
INCONCLUSIVE or a genuine BREACH, only rejects a fabricated COMPLIANT),
a genuinely-unresolvable `.invalid` host -> INCONCLUSIVE (real DNS
failure, not simulated), and a multi-validator agreement assertion read
directly off the transaction receipt's `consensus_data.votes`.

**What actually happened when run** (`gltest tests/integration/ -v -s
--network localnet`, against `glsim` from `genlayer-test==0.29.2`, the
only network reachable in this sandbox — `studio.genlayer.com` needs
outbound network the harness had at debug time but no `genlayer` CLI
account/session was authenticated for it, and testnet_bradbury needs a
funded account, browser-faucet-only, not available here):

**7 tests written, 7 skipped by design** (never faked as passing) — the
`payable_value_status` session canary in `conftest.py` deploys the real
contract and sends a real positive call value to `create_loan()`, checks
whether `principal_deposited` actually reflects it, and skips every test
with a precise reason when it doesn't. In this sandbox it doesn't, for a
confirmed, source-cited reason:

1. **GLSim never forwards transaction `value` into `gl.message.value`.**
   Read `glsim/server.py::_rpc_eth_send_raw_transaction` (from
   `genlayer-test==0.29.2`'s bundled `glsim` package): it decodes the raw
   Ethereum transaction and extracts `code`/`calldata`, but never reads
   `eth_tx["value"]` at all. It calls `engine.deploy_from_code(code_bytes,
   calldata_bytes, sender)` and `engine.call_from_calldata(recipient,
   calldata_bytes, sender)` (`glsim/engine.py`) — neither function even
   accepts a `value` parameter in its signature. Every
   `@gl.public.write.payable` call therefore executes with
   `gl.message.value == 0` regardless of what was sent, which every real
   payable path in `covenant_watch.py` correctly rejects
   (`_require(principal > 0, ...)` etc.) — confirmed by direct inspection
   of the resulting transaction receipts, not guessed. This is an infra
   gap in that specific local simulator build, not a contract bug —
   `tests/direct/` already proves the payable/escrow logic is correct
   against the reference harness.
2. A second, separate, and apparently non-deterministic bug was also hit
   during development of this suite: even a single, first-ever deploy of
   `covenant_watch.py` against a completely fresh `glsim` process
   sometimes fails with `"class is not marked for usage within storage"` —
   the same error text that (correctly) indicates the process-wide
   "only one contract class" loader global from `gltest.direct.loader`
   (documented in the Direct-mode tests section above) is in a bad state,
   but it was observed even on a from-scratch server before any second
   contract class was ever loaded. `run_glsim_patched.py` (a launcher that
   resets that global before every load, mirroring the exact same fix
   already applied in `tests/direct/conftest.py`) reliably fixes the
   documented multi-class case but did not make this intermittent
   single-class failure fully disappear across repeated fresh-server
   restarts in this sandbox. This looks like a genuine `glsim`
   packaging/version-skew issue in this environment, not something fixable
   from test code.
3. `get_contract_schema_for_code` (glsim's static schema introspection,
   which `ContractFactory.deploy()`/`.build_contract()` normally relies on
   to generate a `Contract`'s callable Python methods) also returns an
   empty `methods: {}` for every contract here — `glsim`'s
   `_extract_sdk_schema` filters on a `__gl_public__` attribute that this
   `genlayer` SDK build does not set on `@gl.public.write`/
   `@gl.public.view`-decorated methods. Worked around in
   `tests/integration/conftest.py::deploy_with_manual_schema` by hand-
   writing both contracts' method schemas and building the `Contract`
   wrapper directly via `Contract.new(address, schema, account)` — this
   workaround is unrelated to (1) and (2) and is unaffected by them.
4. No `OPENAI_API_KEY` (or other LLM provider key) was present in this
   sandbox's environment either, which would separately block every
   OFFCHAIN-path test's `gl.nondet.exec_prompt()` call even if (1) and (2)
   were fixed — `llm_provider_status`/`require_llm` in `conftest.py`
   canary-checks and skips for this too, independently of the payable
   canary.

**Exact commands for the user to actually execute this suite for real**,
on a machine/environment without these gaps:

```bash
# Preferred: studio.genlayer.com — hosted, no local glsim version-skew
# risk, no Docker, gasless (0 GEN is fine).
genlayer init                 # authenticate a Studio account, if not done
gltest tests/integration/ -v -s --network studionet

# Alternative: a local GLSim where you've confirmed (or fixed) real value
# forwarding and schema introspection — check your installed version
# against a newer `genlayer-test` release first:
pip install --upgrade "genlayer-test[sim]"
export OPENAI_API_KEY=sk-...
python tests/integration/run_glsim_patched.py --port 4123 --validators 5 \
  --llm-provider openai:gpt-4o-mini
# in another shell:
gltest tests/integration/ -v -s --network localnet

# Real testnet (funded accounts required; faucet claim is browser-based,
# cannot be automated — fund ACCOUNT_PRIVATE_KEY_1/2 in a local .env first):
gltest tests/integration/ -v -s --network testnet_bradbury
```

If `studionet` also fails there for an unrelated reason, run
`genlayer receipt --stdout --stderr <tx-hash>` on the failing transaction
first per the builder-resources debugging workflow, before assuming the
contract itself is at fault — the canaries in `conftest.py` are written to
tell you precisely which capability (payable forwarding vs. LLM provider)
is missing rather than leaving you to guess.

## `DEPLOYMENT.md`: DONE (repo root)

Consolidated runbook covering, in order: (1) GenLayer contract deploy via
`genlayer-cli` (no Docker mentioned anywhere, per spec) with
`genlayer deploy` / `genlayer schema` / `genlayer call` / `genlayer write`
smoke-test examples: (2) wiring `CONTRACT_ADDRESS` (backend) /
`NEXT_PUBLIC_CONTRACT_ADDRESS` (frontend) from the real deployed address
`0x078485282E589a2cb43F6D3263753402045b7192`; (3) backend Fly.io deploy —
folded in verbatim from `backend/DEPLOYMENT_BACKEND.md` (which remains the
canonical backend-only copy; the two must not be allowed to drift — update
both if backend deploy steps change); (4) frontend Vercel deploy — written
as an explicit **pending placeholder** since `frontend/` is still empty as
of this session (nothing fabricated ahead of that work); (5) Postgres
provisioning on Fly (`fly postgres create`/`attach`, plus an external-
managed-Postgres alternative); (6) a post-deploy verification checklist
mirroring JUDGE.md's Human Verification Checklist item-for-item (live app
loads, main flow usable, wallet connection, correct network, reaches the
real contract, transaction lifecycle understandable, errors understandable,
contract address correct everywhere, deployed methods match submitted
source, no mock/simulated integration).

## Pending (not completed this session)

- Integration tests could not be confirmed PASSING in this sandbox (see
  above) — they are real, complete, and will run once pointed at an
  environment without the specific `glsim` build's payable-forwarding gap
  (or given a configured LLM provider key + a working local glsim). Do not
  re-attempt fixing glsim's internals from within this repo — it is an
  external package version issue, not something this project's code can
  paper over without faking results.
- Frontend write flows were not clicked through end-to-end with a real
  signed transaction (no real browser wallet extension in this sandbox).
  See the new "Frontend" section below for exactly what was/wasn't
  verified.

## Commit log (meaningful milestones)

- Verified contract lint-clean, fixed and verified all direct-mode tests
  (26 passed / 1 documented skip), added `.gitignore`, wrote this file.
- Wrote real (non-mocked) `tests/integration/` suite (7 tests) covering
  full happy path, ONCHAIN cross-contract check, adversarial/hostile
  OFFCHAIN content, unreachable-source INCONCLUSIVE, and multi-validator
  consensus; added environment canaries that skip (never fake) tests this
  sandbox's `glsim` build cannot support, with source-cited reasons and
  exact commands to run for real elsewhere. Wrote consolidated
  `DEPLOYMENT.md` at repo root, folding in the backend agent's
  `DEPLOYMENT_BACKEND.md`.

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

## Backend: Redis-backed GenLayer RPC budget + distributed rate limiting
## (this session, 2026-09-21)

GenLayer's RPC has an account/endpoint-wide limit of 5000 requests/hour.
The backend previously made genlayer-py calls (indexer poll loop) with
zero coordination against this — a real production risk given multiple
Fly.io machines could run concurrently. A real, live Upstash Redis
instance was provided for coordination (`REDIS_URL`, `rediss://` TLS,
value lives only in `backend/.env`, confirmed gitignored via root
`.gitignore` line 5 covering `.env` — never committed; see verification
below).

### What was built

- **`app/services/rpc_budget.py`** (new): the shared hourly RPC budget
  tracker. Fixed UTC-hour window key `genlayer:rpc_budget:<epoch_hour>` in
  Redis, `INCR` (atomic) + `EXPIRE ... NX` (TTL set once, no reset race).
  Capped at `GENLAYER_RPC_HOURLY_BUDGET` (new config field, default 4000,
  under GenLayer's 5000/hour ceiling). Raises `RpcBudgetExhaustedError`
  (carries `used`/`limit`/`retry_after_seconds`) when over budget. **Fails
  open** on a Redis-layer outage (logs loudly, allows the call) rather
  than taking the app down — GenLayer's own RPC still hard-rejects if the
  real limit is exceeded.
- **Single choke point**: `call_contract_view_budgeted()` in
  `app/services/chain_client.py`, the deliberate parallel to the
  contract's own `_send_gen` single choke point for fund movement (see
  Escrow section above — same pattern, different domain: no genlayer-py
  call happens without going through this function, the way no GEN moves
  without going through `_send_gen`). Both `chain_client.read_contract_view`
  (request-time live reads) and `app/workers/indexer.py::_call_view` (the
  poll loop — previously called `client.read_contract` directly,
  bypassing any coordination) now funnel through it.
- **Graceful degradation**: indexer catches `RpcBudgetExhaustedError`
  specifically in `indexer_loop`, logs a clear `warning`-level
  `indexer.rpc_budget_exhausted_backing_off` message (not swallowed at
  debug level), sets `_STATUS["state"] = "rate_budget_exhausted"`, and
  sleeps until the actual window reset instead of the normal short poll
  interval — never crashes, never busy-spins. Any request-time code path
  that raises the same error is caught by a new global FastAPI exception
  handler (`app/main.py`) returning a typed `503` with a `Retry-After`
  header — not a generic 500 or a hang.
- **slowapi upgraded to Redis-backed storage**: confirmed directly against
  the installed `slowapi==0.1.9` / `limits==5.8.0` that `Limiter(...,
  storage_uri=...)` is real, supported API (not guessed) and that `limits`
  handles `rediss://` natively. All three `Limiter(...)` instantiations
  (`app/main.py`, `app/api/auth.py`, `app/api/covenants.py`) now pass
  `storage_uri=settings.REDIS_URL` so per-address limits are consistent
  across Fly.io machines instead of each one keeping an independent
  in-process counter.
- **Observability**: `/healthz` extended with an `rpc_budget` field
  (used/limit/remaining/window_reset_seconds/window_reset_at_epoch); same
  data also available standalone at `GET /internal/rate-budget`.
- **Config**: `REDIS_URL` (default `redis://localhost:6379/0` placeholder)
  and `GENLAYER_RPC_HOURLY_BUDGET` (default `4000`) added to
  `app/core/config.py` and `.env.example`, with `.env.example` explicitly
  commenting that production uses a real Upstash `rediss://` URL supplied
  out-of-band, never committed.
- **docker-compose.yml**: added an optional local `redis:7-alpine` service
  (no Upstash account needed for `docker compose up`) and overrides the
  `backend` service's `REDIS_URL` to point at it by default; documented
  the tradeoff (compose-local vs. real Upstash for local dev) in
  `backend/README.md`.
- **Dependencies**: `redis==5.2.1` + `limits[redis]==5.8.0` added to
  `requirements.txt`; `fakeredis==2.38.0` added to `requirements-dev.txt`
  for the new unit tests only.

### How this was verified against REAL infrastructure (not just code review)

1. Connected directly with `redis.from_url(REDIS_URL)` to the real Upstash
   instance and confirmed `PING` → `True`, plus a real `SET`/`GET`
   round-trip over `rediss://` TLS.
2. Called `app.services.chain_client.read_contract_view("get_loan_count")`
   directly against the live deployed contract
   (`0x078485282E589a2cb43F6D3263753402045b7192`) — got a real `0` back
   (correct, no loans on it yet) — and confirmed via a **separate, raw**
   Redis client read (bypassing this project's own status-reporting code)
   that key `genlayer:rpc_budget:<hour>` went from unset to `1` in the
   live Upstash instance.
3. Separately called `app.workers.indexer._call_view(...)` — the exact
   function the indexer's `run_sync_once()` poll loop uses in
   production — directly against the same live contract, and confirmed
   the same Redis key incremented again (`1` → `2`). This specifically
   exercises the indexer's code path, not just the request-time path.
4. Started the real FastAPI app (`uvicorn`) locally with `REDIS_URL`
   pointed at the live Upstash instance and confirmed `GET /healthz` and
   `GET /internal/rate-budget` report the exact same numbers as the raw
   Redis reads above.
5. Hit `POST /auth/nonce` four times against the running app and confirmed
   — via a raw Redis client, not by trusting HTTP status codes — a real
   key `LIMITS:LIMITER/127.0.0.1//auth/nonce/10/1/minute` existed in the
   live Upstash instance with value `4`, proving slowapi's Redis storage
   is genuinely wired up (the 500s on that endpoint were an unrelated
   pre-existing local Postgres auth misconfiguration on this sandbox's
   port-5544 Docker Postgres — `fe_sendauth: no password supplied` — not
   caused by this change; confirmed by reading the traceback, which fails
   inside `db.execute`/session handling, after the rate limiter already
   ran).
6. `pytest tests/` → **15 passed** (the pre-existing 10 + 5 new
   `tests/test_rpc_budget.py` tests using `fakeredis`, so the suite
   doesn't have to hit real Upstash every run): normal increments,
   `RpcBudgetExhaustedError` raised with a correct `retry_after_seconds`
   once over budget, status reads never increment, fail-open behavior
   under a simulated Redis outage, and — driving the real
   `app.workers.indexer._call_view` function against a stub chain client
   with the budget pre-filled — confirmation that the indexer's
   graceful-degradation path actually triggers `RpcBudgetExhaustedError`
   rather than silently succeeding or crashing.

### Blocker noted (not this feature's fault, did not block delivery)

Local Postgres in this sandbox (Docker, port 5544) requires a password
this session does not have (`fe_sendauth: no password supplied`), which
is why a full end-to-end `run_sync_once()` indexer pass (DB write step)
could not be exercised live here — pre-existing to this session, unrelated
to Redis/RPC-budget work. Worked around for verification purposes by
calling the indexer's real `_call_view` chain-call function directly
(item 3 above), which is the exact function `run_sync_once()` calls before
ever touching the DB, so the RPC-budget wiring on the indexer's code path
is still genuinely verified end-to-end.

### Secret-handling confirmation

`REDIS_URL`'s real `rediss://...@major-wahoo-290075.upstash.io:6379` value
was written ONLY to `backend/.env` (confirmed `git status --porcelain`
does not list it — root `.gitignore` line 5 covers `.env`/`.env.*`, `git
check-ignore -v backend/.env` confirms the match). Ran `git diff -- backend/`
and a repo-wide `grep -rl` for the credential fragment across every
touched/new file (`app/`, `tests/`, `*.md`, `*.txt`, `*.yml`,
`.env.example`) before considering this done — zero matches outside
`backend/.env` itself.

## Frontend: DONE (this session, 2026-09-21)

`frontend/` is a real Next.js 16 (App Router) + TypeScript + Tailwind v4
app, scaffolded with `create-next-app`, implementing the "Obsidian
Assurance" dark design system as real Tailwind tokens (`src/app/globals.css`
`@theme inline` block — exact hex colors from `DESIGN.md`, Inter for UI
chrome, JetBrains Mono + `tabular-nums` for all onchain numeric/hash data,
4px/8px radii, `1px solid #00F0FF` focus ring).

### Wallet connection: Reown (WalletConnect) AppKit

Per an explicit mid-session instruction, wallet connection uses **Reown
AppKit** (`@reown/appkit`, `@reown/appkit-adapter-wagmi`, `wagmi`, `viem`,
`@tanstack/react-query`), not a bare `window.ethereum` prompt. Project id
`7fe6800bb991ac35adf13217ea901615` is stored as
`NEXT_PUBLIC_REOWN_PROJECT_ID` in `frontend/.env.example`/`.env.local` (the
exact env var name AppKit's own `createAppKit({ projectId })` option
expects — confirmed by reading the installed package's
`dist/types/exports/index.d.ts`, not guessed). `src/lib/appkit.ts` builds a
real `CaipNetwork` from `genlayer-js`'s own `chains.studionet` definition
(id 61999, "Genlayer Studio Network", its real RPC/nativeCurrency/explorer)
via `@reown/appkit/networks`'s `defineChain`, so the wallet-connect chain
config is never invented separately from what genlayer-js itself uses.
`createAppKit(...)` runs at module scope (client-only), not inside a
`useEffect`, because AppKit's own hooks throw if called before
`createAppKit` has run — see `AppShell.tsx`'s mounted-gate below for why
that still doesn't break static prerendering.
**Connecting a wallet via AppKit is explicitly NOT treated as
authentication.** `src/context/WalletContext.tsx` keeps `address` (AppKit
connection) and `sessionAddress` (backend-authenticated) as separate
pieces of state; the header shows "Connect wallet" -> "Sign in" as two
distinct steps, and `signInWithEthereum()` does the real SIWE round trip
(`POST /auth/nonce` -> `personal_sign` via the AppKit-connected wallet's
own EIP-1193 provider from `useAppKitProvider` -> `POST /auth/verify` ->
httpOnly session cookie) against the already-built backend. If the
connected wallet's address ever stops matching the authenticated session
address (account switch, disconnect), the session is treated as
unauthenticated client-side immediately (`WalletContext.tsx`'s
`sessionMatchesWallet` derivation) — never a stale "signed in" state shown
for the wrong address.

Installing `@reown/appkit-adapter-wagmi` pulled in `@wagmi/connectors`'
Coinbase `baseAccount` connector, which imports Coinbase's CDP SDK's
optional x402 payment-scheme dynamic imports (`@x402/core`, `@x402/evm`,
`@x402/svm`) — Turbopack's build-time import resolution fails on these
unless the packages are actually installed, even though nothing in this
app ever exercises that code path. Fixed by installing them as direct
(unused) devDependencies rather than papering over it with a webpack
alias/ignore — genuinely resolvable imports, not a suppressed error.

### Why `AppShell.tsx` exists (mounted-gate, not a workaround for a bug in our code)

AppKit's hooks (`useAppKit`, `useAppKitAccount`, `useAppKitProvider`)
require `createAppKit()` to have already run, which only happens
client-side (`typeof window !== "undefined"` guard in `lib/appkit.ts`).
During Next's build-time static prerender pass `window` is undefined, so
any page tree that calls these hooks during SSR throws. Rather than
disabling static prerendering repo-wide, `src/components/AppShell.tsx`
renders a minimal "Loading Covenant Watch…" placeholder until a
`useEffect` flips a `mounted` flag, and only then renders `<Providers>`
(wagmi + react-query) and the real page tree (including every page that
calls `useWallet()`/`useSigner()`). Confirmed this resolves cleanly:
`npm run build` prerenders `/`, `/loans`, `/loans/new`, `/history`,
`/profile`, `/settings` as static and the two `[id]`/`[covenantId]` routes
as on-demand dynamic, with zero prerender errors.

### Contract wiring (`src/lib/contract.ts`) — read directly from source, not guessed

Every exported function name/argument list matches `contracts/covenant_watch.py`
exactly, re-derived from a full re-read of the relevant methods this
session (not trusted from memory): `create_loan`, `lock_collateral`,
`claim_principal`, `trigger_covenant_check`, `submit_challenge_evidence`,
`finalize_covenant_check`, `repay_loan`, `reclaim_collateral_timeout`,
`cancel_loan`, `claim_settlement`, plus every `@gl.public.view`. Two things
that would have been easy to get wrong from assumption and were instead
confirmed by reading the source:
1. `create_loan`'s `covenants_json` array items take a plain `threshold`
   field (float), NOT a pre-scaled `threshold_scaled` int — the contract's
   own `_validate_covenant_definition` calls `_scale()` internally. An
   earlier draft of `CovenantInput` had this backwards; fixed before it
   shipped.
2. `_loan_dict`/`_covenant_dict`/`_check_dict` return `status` as the
   already-human-readable string the contract itself emits via
   `LOAN_STATUS_NAMES`/`COVENANT_STATUS_NAMES` (e.g. `"BREACH_TIER1"`,
   `"INCONCLUSIVE"`) — never a raw int the frontend would have to decode
   with its own guessed mapping. `src/components/StatusBadge.tsx` keys
   directly off these strings.

`src/lib/genlayer.ts` confirms the real installed `genlayer-js` API by
reading `node_modules/genlayer-js/dist/*.d.ts` directly (not the training
cutoff's memory of an earlier SDK version): `createClient({chain,
provider})`, `client.readContract(...)`, `client.writeContract(...)`,
`client.waitForTransactionReceipt(...)`, and the real
`chains.studionet`/`chains.localnet`/etc. exports. `src/lib/tx.ts` drives
every write through `submitted -> pending -> finalized/failed` off the
SDK's own `waitForTransactionReceipt` status (`TransactionStatus` enum
values `CANCELED`/`VALIDATORS_TIMEOUT`/`LEADER_TIMEOUT`/`UNDETERMINED`
treated as failure) — never a `setTimeout` standing in for status, per the
working rules.

### Pages built (all real, all wired to the real contract + real backend cache)

`/` (landing), `/loans` (dashboard, backend-cached list with a live
Collateral Health Gauge per loan), `/loans/new` (full covenant-builder
form: per-covenant source type/ref/condition/operator/threshold, live
SSRF-protected preview of OFFCHAIN URLs via the backend's
`/covenants/preview-source`, client-side vague-condition-phrase rejection
mirroring the contract's own `VAGUE_CONDITION_FRAGMENTS` list, bounded
challenge-window slider, tiered consequence schedule inputs), `/loans/[id]`
(detail + every lifecycle action gated on session address vs.
lender/borrower — lock collateral, claim principal, repay, cancel,
reclaim-on-timeout, claim settlement), `/loans/[id]/covenants/[covenantId]/check`
(trigger button respecting the real on-chain cooldown via
`get_cooldown_remaining`, real Pinned Snapshot Hash component, Validator
Consensus Split Meter fed from the transaction receipt's consensus data
when present, real INCONCLUSIVE state treatment — distinct slate badge,
explicit "not a breach and not compliance" copy), `/loans/[id]/covenants/[covenantId]/challenge`
(structurally additive-only: the form has no field that can edit/replace
the original pinned source or prior evidence, only an "add more evidence"
input; real challenge-window countdown from the real
`challenge_window_ends_at` chain field), `/history` (cross-loan check/
challenge history from the backend cache), `/profile` (session address +
the user's loans by role), `/settings` (network/contract/backend health +
sign-out + an explicit, honest "deferred (out of v1 scope)" list — no
faked functionality).

### Verified this session (actually run, not just written)

- `npm run build` — clean, all 10 routes compile and either statically
  prerender or correctly mark as on-demand dynamic (the two `[id]`/
  `[covenantId]` param routes).
- `npm run lint` — zero errors/warnings after fixing two real issues it
  caught: a `set-state-in-effect` pattern in the original
  `WalletContext.tsx` (refactored to a derived value instead of a second
  effect) and a `BigInt` / ES2020 target mismatch in `tsconfig.json`
  (bumped from `ES2017`).
- A live dev server (`npm run dev`, Node 22 via nvm — the sandbox's system
  `node` is 18.20.8 which Next 16 refuses to run; `.claude/launch.json` at
  the repo root pins the dev command to a `PATH`-prefixed Node 22 binary)
  was opened in the actual Browser pane: landing page text confirmed
  correct including the live `NEXT_PUBLIC_CONTRACT_ADDRESS` display,
  `/loans/new`'s full form rendered with every field described above, and
  clicking "Connect wallet" opened the real Reown AppKit modal listing
  real wallet options (Trust Wallet, MetaMask, Binance Wallet, SafePal,
  "Search Wallet 80", "UX by reown" footer) — confirming the project id is
  live and AppKit is correctly wired, not a placeholder. Console showed
  only the expected `ERR_CONNECTION_REFUSED` from the backend not running
  in that check — no React/render errors.

### NOT verified in this sandbox (documented rather than faked)

- No real browser wallet extension exists in this sandbox to actually
  approve a `personal_sign` SIWE request or a `writeContract` transaction
  (e.g. clicking through a real `create_loan`). Every write path is real
  code (genlayer-js `writeContract`, real tx-hash-returning calls, no
  mocked signer, no fabricated receipt) — this is a capability gap in the
  sandbox, not a simulated integration in the app. After deploying, a
  human must click through `DEPLOYMENT.md`'s Human Verification Checklist
  with a real wallet.
- The backend was not running during the browser smoke test above, so
  `/auth/*`-dependent UI states (post-sign-in header, `/loans` populated
  list, `/history`, `/profile`) were not visually confirmed against live
  data in this session — only their code paths and the loading/empty/error
  branches were exercised by inspection. Start the backend locally (see
  its own "Exact local-dev commands" above) alongside `npm run dev` to
  confirm end-to-end once a wallet is available too.
- The 6 prototype HTML files named in the task brief
  (`covenant_watch_protocol_landing_page.html`,
  `originate_loan_covenants.html`, etc.) were not found anywhere under
  `/Users/macbook/Downloads` in this sandbox (searched exhaustively) — the
  IA for each page was built directly from the master spec's §13 quality
  bar and `DESIGN.md`'s component specs instead, not copied from a
  prototype that didn't exist here. The emblem/logo (`src/components/
  Emblem.tsx`, `src/app/icon.svg`) is an original hexagonal-seal SVG design
  in the Obsidian Assurance palette, not extracted from a prototype file.
  **CORRECTED in a later session (see "Correction pass" below): the files
  actually exist at `/Users/macbook/Documents/stitch_dark_theme_project_design/`
  — wrong search directory, not a missing-file problem.**

### Correction pass: prototypes found at the correct path (2026-09-21, later session)

The 6 prototype HTML files (plus `DESIGN.md`) actually live at
`/Users/macbook/Documents/stitch_dark_theme_project_design/`, not
`/Users/macbook/Downloads` as the earlier session searched. Read all 6 in
full this pass and reconciled the built frontend against their
information architecture (content/structure/fields — not their raw
markup or exact colors; `DESIGN.md`'s tokens, already implemented,
remained authoritative for visual styling). Net changes:

- **Emblem/logo/favicon — the one substantive fix.** `covenant_watch_emblem.html`
  turned out to be a real, self-contained SVG (hexagon shield, concentric
  "watch iris" rings, 3 satellite validator nodes, reticle crossbars) —
  not just a described graphic. `src/components/Emblem.tsx` and
  `src/app/icon.svg` were rebuilt to faithfully match that geometry
  (recolored onto the existing Obsidian Assurance tokens, not copied
  byte-for-byte), replacing the earlier session's invented hexagonal-seal
  design. `src/app/favicon.ico` (16/32px) and a new
  `src/app/apple-icon.png` (180px) were regenerated from the new
  `icon.svg` via `rsvg-convert`/`imagemagick` so all three logo surfaces
  (in-app header, browser tab, iOS home screen) are now actually derived
  from the same prototype-sourced mark.
- **Landing page (`src/app/page.tsx`):** added the "why undercollateralized
  lending breaks today" old-world-vs-Covenant-Watch comparison section
  from `covenant_watch_protocol_landing_page.html`'s Section 2 — this was
  genuinely absent (the built page only had the core-loop steps + 3
  feature cards). Kept the existing hero, core loop, and feature cards as-is
  since they already covered the prototype's other key IA.
  `originate_loan_covenants.html`'s hero-terminal telemetry mock, KPI
  ribbon, and code-sample sections were judged marketing flourish on top
  of already-covered ground and left out to avoid bloating a page that's
  meant to stay lean and real-data-driven.
- **Loans list (`src/app/loans/page.tsx`):** added a small real-data KPI
  row (total escrowed, loan count, in-grace count, breached count — all
  computed client-side from the already-fetched `loans` array, no new
  API calls) and status filter tabs (All/Compliant/Grace/Breach, bucketed
  from the real `loan.status` enum), matching
  `active_credit_lines_covenant_health.html`'s KPI ribbon + filter bar
  IA that the built page was missing entirely.
- **Loan origination (`src/app/loans/new/page.tsx`):** added a
  "Pre-deployment summary" card (principal, collateral, interest, covenant
  count — all read from existing form state, nothing new fetched) before
  the submit button, matching `originate_loan_covenants.html`'s
  "Pre-Deployment State" review panel IA. The rest of the origination
  flow (counterparty, per-covenant source/threshold/tier fields, vague-
  condition rejection, challenge window) already matched the prototype's
  covenant-builder structure field-for-field and was left alone.
- **Left unchanged after review:** `loans/[id]/page.tsx` (loan detail),
  the covenant check page (already has `SnapshotHash` + `ConsensusMeter`
  + observed-value + challenge-window content matching
  `covenant_check_verification.html`'s pinned-source/consensus/consequence
  structure), and the challenge/dispute page (already additive-only
  evidence form matching `dispute_challenge_portal.html`'s core IA — its
  evidence-type tabs and historical-disputes-archive table were skipped
  since the real contract's `submit_challenge_evidence` only accepts a
  URL + note, and there's no backend endpoint for a global disputes
  archive; adding either would mean fake, unwired UI).
- `npm run build` and `npm run lint` both verified passing after these
  changes.

### Exact local-dev commands

```bash
cd frontend
npm install
cp .env.example .env.local
# .env.local defaults already point at the live deployed contract
# (0x078485282E589a2cb43F6D3263753402045b7192, studionet) and the real
# Reown project id — only NEXT_PUBLIC_BACKEND_URL needs to match wherever
# you're running backend/ (default http://localhost:8000)

npm run dev      # requires Node >=20.9 — this sandbox's system node is
                  # 18.20.8; a newer node (e.g. via nvm) is required
npm run build    # production build, verified passing in this session
npm run lint     # verified passing in this session
```
