# DEPLOYMENT.md -- backend section

This file is the backend-specific deploy runbook. A separate pass will
fold this into a consolidated repo-root `DEPLOYMENT.md` alongside the
frontend (Vercel) and contract (genlayer-cli) sections -- nothing here
should be lost when that happens.

## Prerequisites

- Fly CLI installed and authenticated to your own account (`fly auth
  whoami` to confirm). This agent does NOT run `fly deploy` -- you do,
  from your own account.
- A Postgres instance reachable from Fly (a Fly Postgres app, or any
  external managed Postgres -- Neon/Supabase/RDS all work since we use a
  plain `DATABASE_URL`).
- The contract already deployed to GenLayer StudioNet (or your target
  network) via `genlayer-cli`, per `contracts/`. This project's own
  deployment is already live at:

  ```
  CONTRACT_ADDRESS=0x078485282E589a2cb43F6D3263753402045b7192
  ```

  (StudioNet -- see repo-root `memory.md` for the deployment record.)
  Use your own address if you redeploy; this is the concrete value this
  project itself is wired to.

## One-time setup

```bash
cd backend
fly launch --no-deploy   # creates the app from fly.toml, does NOT deploy yet
                          # rename `app = "covenant-watch-backend"` in fly.toml
                          # first if that name is taken

fly secrets set \
  DATABASE_URL="postgresql+psycopg://<user>:<pass>@<host>:5432/<db>" \
  SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  CONTRACT_ADDRESS="0x078485282E589a2cb43F6D3263753402045b7192" \
  GENLAYER_NETWORK="studionet" \
  CORS_ALLOWED_ORIGINS="https://<your-frontend>.vercel.app" \
  COOKIE_DOMAIN="<your-api-domain-or-leave-unset-for-apex>" \
  SENTRY_DSN=""   # optional, leave empty for the safe no-op path
```

## Deploy

```bash
fly deploy
```

`fly.toml`'s `[deploy].release_command = "alembic upgrade head"` runs
migrations automatically before the new machine takes traffic. The
`[http_service]` block sets `min_machines_running = 1` and
`auto_stop_machines = false` so this is a 24/7 always-on service, not a
scale-to-zero one, with an HTTP health check against `/healthz` gating
rollout.

## Post-deploy verification checklist

- `curl https://<your-app>.fly.dev/healthz` -> `"status":"ok"`,
  `"database":"ok"`, and once `CONTRACT_ADDRESS` is set,
  `"indexer":{"state":"idle"|"syncing", ...}` (not stuck on
  `waiting_for_contract_address` or `error`).
- `fly logs` -> confirm structured JSON log lines, no repeated tracebacks.
- Hit `/auth/nonce` then `/auth/verify` with a real wallet from the
  frontend and confirm the session cookie round-trips (Secure,
  SameSite=Strict, httpOnly -- check via browser devtools, not just
  status code).
- Confirm `/loans` returns `[]` cleanly (not an error) before the indexer
  has caught up, and starts returning real rows once `get_loan_count() >
  0` on-chain.
- If you ever need to rebuild the cache from scratch: connect to Postgres
  and run `UPDATE sync_cursor SET last_synced_loan_id = 0 WHERE shard_key
  = 'default';`, then restart the Fly machine -- the indexer re-walks
  every loan from chain state.

## What was verified locally in this session (not just written)

- `alembic upgrade head` applied cleanly against a real local Postgres 16
  instance (Homebrew, not Docker -- Docker Desktop's daemon was not
  running in this sandbox; docker-compose.yml/Dockerfile are written and
  structurally consistent but not themselves smoke-tested end-to-end).
- Full SIWE auth round trip (nonce -> sign with an ephemeral throwaway
  eth-account test keypair -> verify -> session cookie -> authenticated
  `/auth/me` -> nonce-replay rejection -> wrong-signer rejection) against
  the running FastAPI app.
- SSRF preview endpoint: confirmed it blocks the `169.254.169.254`
  metadata IP, `localhost`, and `file://` scheme, and successfully fetches
  a real public URL.
- `/healthz` reporting `waiting_for_contract_address` with no
  `CONTRACT_ADDRESS` set, then a live indexer sync pass (`state: idle`,
  `last_success_at` populated, no error) against the **real deployed
  contract** at `0x078485282E589a2cb43F6D3263753402045b7192` on StudioNet
  -- `get_loan_count()` returned `0` (no loans created on it yet), which
  is the correct, non-fabricated result.
