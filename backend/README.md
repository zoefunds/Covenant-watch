# Covenant Watch -- Backend

FastAPI + PostgreSQL backend for Covenant Watch. See repo-root `memory.md`
for full project context; this file covers only the backend module.

## Cache vs. live: the pattern you must follow

Postgres is a **read-optimized cache**, populated by the indexer worker
(`app/workers/indexer.py`) polling the deployed contract's view methods.
It is **never** the source of truth for money or compliance state, and it
can lag the chain by up to `INDEXER_POLL_INTERVAL_SECONDS`.

- Use the REST API (`/loans`, `/covenants/...`, `/loans/{id}/checks`, ...)
  for fast list/detail reads -- dashboards, history, browsing.
- For anything money-relevant where staleness would be a problem (e.g.
  "am I allowed to claim right now", "has this loan already been
  finalized"), the **frontend must re-read the contract directly** via
  genlayer-js immediately before submitting a transaction, not trust the
  cached value. `app/services/chain_client.py::read_contract_view` is the
  backend-side equivalent for any server-side code that needs a
  guaranteed-fresh answer.
- The cache can always be safely rebuilt from genesis: reset the single
  row in `sync_cursor` (`last_synced_loan_id = 0`) and let the indexer
  re-walk every loan.

## Auth model

Wallet-signature auth (SIWE-style), not "connected wallet = authenticated":

1. `POST /auth/nonce {address}` -> single-use nonce stored in Postgres
   (`nonces` table), 5 minute TTL.
2. Frontend has the wallet sign the returned message.
3. `POST /auth/verify {address, signature, message}` -> recovers the
   signer via `eth_account.Account.recover_message`, checks it matches
   `address`, checks the embedded nonce is unused/unexpired, marks it
   used, creates a `sessions` row, and sets an httpOnly, Secure (in prod),
   SameSite=strict signed cookie.
4. Every protected route depends on `app.api.deps.require_session`, which
   resolves that cookie back to a live, unrevoked `Session` row. A bare
   wallet address in a request body is never trusted on its own.

## Rate limiting is NOT the enforcement boundary

`slowapi` rate limits on `/auth/*` and write-adjacent endpoints are
defense-in-depth only (against brute-force/spam), same for the
`rate_limit_counters` table (UX mirror of the contract's own cooldown, to
gray out a button early). The contract's own `get_cooldown_remaining` /
on-chain checks are the real enforcement point and cannot be bypassed by
hitting the API directly.

## SSRF-protected URL preview

`POST /covenants/preview-source {url}` (`app/services/url_preview.py`) is
purely informational -- shown to a loan creator before pinning an offchain
source. It resolves DNS itself and blocks private/loopback/link-local/
reserved ranges (including the `169.254.169.254` cloud metadata IP) on
every redirect hop, not just the input URL string. It never feeds the
contract's own independent fetch/consensus at check time.

## Local development

```bash
cd backend
cp .env.example .env   # edit SESSION_SECRET at minimum; CONTRACT_ADDRESS
                        # stays blank until you deploy the contract yourself

# Option A: docker-compose (Postgres + Redis + migrate + backend)
docker compose up --build

# Option B: local Postgres + venv (what this session actually smoke-tested)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# point DATABASE_URL at your local Postgres, then:
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`GET /healthz` reports DB connectivity, indexer liveness/state
(`waiting_for_contract_address` until `CONTRACT_ADDRESS` is set), and the
current GenLayer RPC hourly budget usage (`rpc_budget`, also available
standalone at `GET /internal/rate-budget`).

## GenLayer RPC hourly budget + distributed rate limiting (Redis)

GenLayer's RPC has an account/endpoint-wide limit of 5000 requests/hour.
Since this backend can run multiple Fly.io machines plus a continuously
polling indexer, an in-process counter isn't enough -- all instances need
to agree on how much of the hourly budget is left. Redis is the shared
coordination point for two independent things:

1. **Outbound genlayer-py RPC budget** (`app/services/rpc_budget.py`).
   Every genlayer-py call in this codebase funnels through ONE choke
   point, `call_contract_view_budgeted()` in `app/services/chain_client.py`
   -- used by both the indexer's poll loop (`app/workers/indexer.py::_call_view`)
   and any request-time live read (`chain_client.read_contract_view`).
   This is the deliberate parallel to the contract's own `_send_gen`
   single choke point for fund movement (see repo-root `memory.md`): no
   code path calls genlayer-py without going through this function first,
   the same way no code path moves GEN without going through `_send_gen`.
   Grep for `check_and_increment_rpc_budget` to find every outbound RPC
   call site.
   - Fixed hourly window keyed by wall-clock UTC hour
     (`genlayer:rpc_budget:<epoch_hour>` in Redis), capped at
     `GENLAYER_RPC_HOURLY_BUDGET` (default 4000, comfortably under
     GenLayer's 5000/hour ceiling). `INCR` (atomic) + `EXPIRE ... NX`
     (only sets TTL once, so concurrent first-callers can't reset each
     other's window).
   - **Graceful degradation, never a crash or busy-spin**: if the indexer
     hits an exhausted budget, it logs a clear `warning`-level
     `indexer.rpc_budget_exhausted_backing_off` message, skips the rest of
     that poll cycle, and sleeps until the budget window actually resets
     (not the usual short poll interval) before trying again automatically
     -- see `indexer_loop` in `app/workers/indexer.py`. A request-time live
     read that would exceed budget raises `RpcBudgetExhaustedError`, caught
     by a dedicated FastAPI exception handler in `app/main.py` that returns
     a typed `503` with a `Retry-After` header (not a generic 500 or a
     hang).
   - **Fails open** on a Redis outage (logs loudly, allows the call) --
     a coordination-layer blip should degrade to "no coordination" (the
     old behavior) rather than taking the whole app down.
2. **slowapi rate limiting** (`app/main.py`, `app/api/auth.py`,
   `app/api/covenants.py`). Previously in-process only, meaning each
   Fly.io machine kept an independent counter -- upgraded to Redis-backed
   storage via `Limiter(..., storage_uri=settings.REDIS_URL)` (confirmed
   against the installed `slowapi==0.1.9` / `limits==5.8.0` API directly,
   not guessed) so per-address/per-endpoint limits are now consistent
   across every instance. This remains defense-in-depth only -- the
   contract's own on-chain cooldown is still the real enforcement
   boundary, unchanged from before.

**Local dev**: `docker-compose.yml` includes an optional local `redis`
service (no Upstash account needed to run `docker compose up`) and
overrides `REDIS_URL` to point at it. Running the backend directly via a
venv (Option B above) needs `REDIS_URL` set in `.env` -- either point it
at that same local Redis (`docker compose up redis` alone, then
`REDIS_URL=redis://localhost:6379/0`), or at the real Upstash instance;
either works identically since the app only needs `INCR`/`EXPIRE`/`GET`.
**Production always uses a real Upstash `rediss://` TLS URL, supplied
out-of-band directly into `backend/.env` (or the Fly.io secret) -- never
committed.** `.env.example` only ever has a `redis://localhost:6379/0`
placeholder.

### How this was verified (real infra, not just code review)

- Connected directly to the real Upstash instance with `redis.from_url(...)`
  and confirmed `PING`/`SET`/`GET` succeed over `rediss://` TLS.
- Called `app.services.chain_client.read_contract_view("get_loan_count")`
  and separately `app.workers.indexer._call_view(...)` directly against the
  live deployed contract (`0x078485282E589a2cb43F6D3263753402045b7192`,
  StudioNet) and confirmed both real genlayer-py calls succeeded AND the
  shared `genlayer:rpc_budget:<hour>` Redis key incremented -- inspected
  directly with a raw `redis-cli`-equivalent Python client call, not just
  trusted from logs or from `get_rpc_budget_status()`.
- Confirmed `GET /healthz` and `GET /internal/rate-budget` report the same
  numbers as that direct Redis inspection.
- Hit `POST /auth/nonce` four times against a locally-running instance and
  confirmed a real slowapi key (`LIMITS:LIMITER/127.0.0.1//auth/nonce/10/1/minute`)
  appeared in the live Upstash instance with a value of `4`, inspected
  directly via the Redis client -- not just inferred from HTTP responses.
- Ran the full `pytest` suite (15 passed) including 5 new
  `tests/test_rpc_budget.py` tests, which use `fakeredis` (in-memory,
  no real network) to cover: normal increments, hitting the exhausted-budget
  exception with the correct `retry_after_seconds`, that status reads never
  increment, fail-open behavior on a simulated Redis outage, and that
  `app.workers.indexer._call_view` (the real indexer code path) surfaces
  `RpcBudgetExhaustedError` correctly when the budget is filled.
- Local Postgres in this sandbox has an unrelated pre-existing auth
  misconfiguration (`fe_sendauth: no password supplied` on port 5544, a
  Dockerized Postgres from a prior session) that blocked a full end-to-end
  indexer poll cycle through `run_sync_once()` (which touches the DB before
  the chain). This is NOT related to this change -- verified by calling the
  indexer's exact `_call_view` chain-call function directly (bypassing only
  the DB step) against the live contract, which is the same function
  `run_sync_once()` calls in production.

## Picking up `CONTRACT_ADDRESS` after you deploy

The indexer checks `CONTRACT_ADDRESS` on every poll loop iteration but
config is loaded once per process (`lru_cache`d `Settings`). **Supported
reload path: restart the process** (or redeploy on Fly, which restarts
the machine) after setting the env var / Fly secret -- this was a
deliberate choice over hot-reloading config, since a stale cached
`CONTRACT_ADDRESS` silently pointing at the wrong contract is a much worse
failure mode than a 10-second restart.

## Tests

`tests/` contains service-level tests (SSRF blocklist logic, SIWE message
parsing) that don't require a live Postgres. The full auth round-trip and
migration-apply were smoke-tested manually against a real local Postgres
instance during development (see repo-root `memory.md`), not against a
mocked DB.
