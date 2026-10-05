# Covenant Watch — Backend

FastAPI, PostgreSQL, Redis, and an indexer for Covenant Watch. Production is
`https://covenant-watch-api.fly.dev` (`covenant-watch-api`, Fly region `iad`).

## Authority boundary

The backend is not a transaction relayer and has no funded contract signer.
It cannot create or mutate loans, decide covenant results, apply penalties,
move escrow, submit challenges, or finalize checks. Those operations are sent
from the user's wallet directly to the GenLayer contract and enforced there.

The backend provides:

- a rebuildable PostgreSQL read cache for lists, profiles, and history;
- SIWE-style nonce, signature verification, and session cookies;
- an informational SSRF-protected URL preview;
- indexer health and a shared outbound RPC budget.

Never use cached data to decide whether a money-moving action is currently
allowed. The frontend rereads finalized contract state before/after writes, and
the contract rechecks every rule regardless of UI or cache state.

## Indexed cache

`app/workers/indexer.py` polls contract views and scopes cached rows to the
configured contract address. `POST /loans/sync` and background polling are
serialized by both an in-process lock and a PostgreSQL transaction advisory
lock, preventing overlap across replicas. A synchronous RPC worker that times
out retains its lease until it actually exits, avoiding replacement-thread
accumulation.

The production poll interval is 300 seconds. A just-finalized transaction can
therefore be visible onchain before it appears in cached list/history routes.
Detail screens explicitly use direct finalized reads when freshness matters.

## Authentication

Wallet connection and authentication are separate:

1. `POST /auth/nonce` creates a single-use nonce with a five-minute TTL.
2. The wallet signs the returned message.
3. `POST /auth/verify` recovers the signer, matches the requested address,
   rejects used/expired nonces, creates a session, and sets a signed httpOnly
   cookie (`Secure` in production, `SameSite=strict`).
4. Protected routes resolve that cookie through
   `app.api.deps.require_session`; a request-body address is never sufficient.

## URL preview and SSRF controls

`POST /covenants/preview-source` is a creation-time convenience only. It
resolves DNS and blocks private, loopback, link-local, reserved, and metadata
addresses on every redirect. Its response is never passed to the contract.
During covenant evaluation each GenLayer leader/validator independently fetches
all immutable source URLs stored by the contract.

## RPC budget and rate limiting

All backend GenLayer reads pass through
`app.services.chain_client.call_contract_view_budgeted`. Redis holds a shared
fixed-window budget (`genlayer:rpc_budget:<epoch-hour>`), configured by
`GENLAYER_RPC_HOURLY_BUDGET` and reported by `/healthz` and
`/internal/rate-budget`.

- Request-time budget exhaustion returns typed HTTP 503 plus `Retry-After`.
- The indexer stops the current pass and waits for the budget reset.
- Redis coordination failure logs loudly and fails open so an auxiliary
  coordination outage does not take the API down.
- SlowAPI also uses Redis so abuse limits are shared across instances. These
  limits are defense in depth; contract cooldowns remain authoritative.

## Configuration

Copy `.env.example` to `.env`. Important values:

- `CONTRACT_ADDRESS=0x5c3Fe893aaaa9C0416F76812c3903Cf4AfA528A7`
- `GENLAYER_NETWORK=studionet`
- `DATABASE_URL` for PostgreSQL
- `REDIS_URL` for shared coordination
- a private, random `SESSION_SECRET`
- `CORS_ALLOWED_ORIGINS=https://covenant-watch.vercel.app`

Settings are process-cached. After changing `CONTRACT_ADDRESS`, restart or
redeploy; silent hot switching between contracts is intentionally unsupported.

## Local development

```bash
cd backend
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/healthz
```

Alternatively, `docker compose up --build` starts the packaged local services.

## Production deployment

```bash
cd backend
fly secrets set \
  CONTRACT_ADDRESS=0x5c3Fe893aaaa9C0416F76812c3903Cf4AfA528A7 \
  -a covenant-watch-api
fly deploy -a covenant-watch-api
curl https://covenant-watch-api.fly.dev/healthz
```

The Fly secret update itself restarts the machine. Run `fly deploy` when source,
dependencies, migrations, or `fly.toml` changed. The release command applies
Alembic migrations before the rolling machine update.

## Verified state

On 2026-10-05:

- all 17 backend tests passed;
- `genlayer-py==0.18.0` matched `requirements.txt`;
- the production Fly machine restarted successfully with the audited address;
- `/healthz` returned `status: ok`, `database: ok`, indexer `state: idle`, a
  populated `last_success_at`, `last_error: null`, and
  `contract_configured: true`.

See root `AUDIT.md` for the complete security/verification report and
`DEPLOYMENT.md` for the cross-component runbook.
