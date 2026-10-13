# Covenant Watch backend deployment

Current production app: `covenant-watch-api` in Fly region `iad`.

## Production configuration

Store credentials as Fly secrets; never commit database, Redis, session, observability, or relayer secrets.

```bash
fly secrets set -a covenant-watch-api \
  CONTRACT_ADDRESS=0xb86d1525014c80F98E7f0C3Be2af60AF3ab761F8 \
  GENLAYER_NETWORK=studionet \
  BASE_SEPOLIA_RPC_URL=https://sepolia.base.org \
  BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e \
  BASE_ESCROW_ADDRESS=0x6b806484E938E8Bf5eD65D1841543931240834ef \
  BASE_RELAYER_PRIVATE_KEY='<secret>' \
  DATABASE_URL='postgresql+psycopg://...' \
  REDIS_URL='rediss://...' \
  SESSION_SECRET='<random-secret>' \
  CORS_ALLOWED_ORIGINS='https://covenant-watch.vercel.app'
```

Settings are process-cached. A contract-address update must restart the machine. Keep Base and GenLayer addresses from the same coordinated deployment; their loan IDs are paired.

## Deploy and migrate

```bash
cd backend
fly deploy -a covenant-watch-api
```

`fly.toml` uses a rolling strategy and runs `alembic upgrade head` as the release command. The always-on machine exposes port 8000 and must pass `GET /healthz` before rollout completes.

## Verify

```bash
curl https://covenant-watch-api.fly.dev/healthz
curl https://covenant-watch-api.fly.dev/loans
fly status -a covenant-watch-api
fly logs -a covenant-watch-api
```

Healthy output includes `status: ok`, `database: ok`, `contract_configured: true`, an indexer state of `idle` or `syncing`, a recent `last_success_at`, and `last_error: null`. On the fresh 13 October 2026 deployment, `/loans` returned an empty list because both contracts started at loan count zero.

## Privilege boundary

- The service reads public GenLayer and Base state and maintains a rebuildable cache.
- The only contract write it signs is a finalized GenLayer decision relayed through Base `applyDecision`.
- It cannot approve USDC, create a loan, stake collateral, claim principal, repay, cancel, mature-settle, or claim user settlement.
- `BASE_RELAYER_PRIVATE_KEY` is a funded testnet secret. Rotate it and call Base `setRelayer` if exposure is suspected.
- Do not scale replicas without retaining the advisory lock, shared Redis RPC budget, and replay checks.

See `backend/README.md` for internals and root `DEPLOYMENT.md` for the full deployment sequence.
