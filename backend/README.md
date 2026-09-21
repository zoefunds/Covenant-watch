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

# Option A: docker-compose (Postgres + migrate + backend)
docker compose up --build

# Option B: local Postgres + venv (what this session actually smoke-tested)
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# point DATABASE_URL at your local Postgres, then:
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`GET /healthz` reports DB connectivity and indexer liveness/state
(`waiting_for_contract_address` until `CONTRACT_ADDRESS` is set).

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
