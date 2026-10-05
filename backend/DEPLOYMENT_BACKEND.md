# Covenant Watch Backend Deployment

Current production app: `covenant-watch-api` in Fly region `iad`.

## Required configuration

Set these as Fly secrets; never commit real database, Redis, session, or
observability credentials:

```bash
fly secrets set -a covenant-watch-api \
  CONTRACT_ADDRESS=0x5aD6959559D0eF030a62C625b9071eBE655af74a \
  GENLAYER_NETWORK=studionet \
  DATABASE_URL='postgresql+psycopg://...' \
  REDIS_URL='rediss://...' \
  SESSION_SECRET='<random-secret>' \
  CORS_ALLOWED_ORIGINS='https://covenant-watch.vercel.app'
```

`CONTRACT_ADDRESS` is public, but it is a secret variable operationally so a
machine restart atomically picks up the new value. Settings are process-cached;
changing the value without restarting is unsupported.

## Deploy source and migrations

```bash
cd backend
fly deploy -a covenant-watch-api
```

`fly.toml` uses a rolling strategy and runs `alembic upgrade head` as the
release command. The single always-on machine exposes port 8000 and must pass
`GET /healthz` before rollout completes.

## Verify

```bash
curl https://covenant-watch-api.fly.dev/healthz
fly status -a covenant-watch-api
fly logs -a covenant-watch-api
```

Healthy output has `status: ok`, `database: ok`,
`contract_configured: true`, an indexer state of `idle` or `syncing`, a recent
`last_success_at`, and `last_error: null`. Also verify the RPC budget is below
its configured limit.

The production secret was updated to the audited contract on 2026-10-05. The
machine restarted successfully and the health response satisfied all fields
above.

## Architecture constraints

- The backend is a read cache/auth/preview service, not a contract writer.
- Indexer passes use process and PostgreSQL advisory locks.
- Do not scale replicas without retaining the distributed lock and shared Redis
  RPC budget.
- Cached state may lag; money-relevant decisions require finalized direct chain
  reads and are always re-enforced by the contract.

See `backend/README.md` for internals and root `DEPLOYMENT.md` for the full
contract/frontend/backend sequence.
