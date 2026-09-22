# Covenant Watch — Deployment Runbook

This is the consolidated deployment runbook: GenLayer contract, backend
(Fly.io), frontend (Vercel), Postgres, and a post-deploy verification
checklist. Every step that touches money, an account, or a live deploy is
run by **you** — this project never deploys or holds credentials on your
behalf.

---

## 1. GenLayer contract deployment

**You run this yourself**, from your own already-authenticated GenLayer
Studio / `genlayer-cli` session with your own testnet GEN. Nothing here
deploys on your behalf.

> Note: `NO DOCKER` — GenLayer Studio's Docker stack is intentionally not
> used or referenced anywhere in this workflow. `genlayer-cli` talks to
> `studio.genlayer.com` (or whichever network you select) over its own
> RPC; it needs no local Docker daemon.

```bash
# One-time: point the CLI at StudioNet and load your account (if not
# already configured — skip if `genlayer account list` already shows one).
genlayer init                    # picks network + creates/imports an account
genlayer account list             # confirm your account + its address

# Deploy contracts/covenant_watch.py to StudioNet using your own
# already-funded/gasless Studio session:
genlayer deploy \
  --contract contracts/covenant_watch.py \
  --network studionet

# The command prints the new contract's address, e.g.:
#   Contract deployed at: 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7
```

This project's own live StudioNet deployment (already done by the user)
is at:

```
0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7
```

Treat this as the concrete example value below — replace it with your own
address if you redeploy.

### Fetch the deployed schema/ABI

```bash
genlayer schema --contract-address 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7 \
  --network studionet
```

This should list all 19 public methods (10 write / 9 view) from
`contracts/covenant_watch.py` — `create_loan`, `lock_collateral`,
`trigger_covenant_check`, `get_loan`, etc. If a method is missing or the
call errors, do not proceed to wiring the backend/frontend — debug first
with:

```bash
genlayer receipt --stdout --stderr <deploy-tx-hash>
genlayer code --contract-address 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7 --network studionet
```

### Smoke-test a read and a write

```bash
# Read: total loan count on the fresh deployment should be 0
genlayer call --contract-address 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7 \
  --network studionet \
  get_loan_count

# Write: create a tiny smoke-test loan (replace <borrower-address> with a
# second account of yours; this sends real principal as call value, so use
# a trivial amount on StudioNet, which is gasless — 0 GEN balance is fine
# for gas, but call value still needs to be a real positive number).
genlayer write --contract-address 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7 \
  --network studionet \
  --value 1000 \
  create_loan \
  --args '<borrower-address>' 2000 500 9999999999 \
    '[{"source_type":"ONCHAIN","source_ref":"0x1111111111111111111111111111111111111111","condition_field":"signer_count","operator":">=","threshold":1,"description":"smoke test covenant","tier1_interest_step_up_bps":500,"tier2_seizure_bps":5000}]' \
  0

# Confirm it landed:
genlayer call --contract-address 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7 \
  --network studionet \
  get_loan_count
# -> should now return 1
```

(Exact `genlayer` CLI flag names can shift between CLI versions — run
`genlayer deploy --help` / `genlayer call --help` / `genlayer write --help`
first if any of the above errors on an unrecognized flag, and adjust
accordingly. The RPC semantics above — deploy, fetch schema, read, write —
are what matters and won't change.)

---

## 2. Wiring the deployed address

The single `CONTRACT_ADDRESS` from step 1 needs to reach both the backend
and the frontend as environment variables — nowhere else. Nothing in this
codebase hardcodes it.

| Where | Variable | File that documents it |
|---|---|---|
| Backend | `CONTRACT_ADDRESS` | `backend/.env.example` (local dev) / Fly secret (prod) |
| Frontend | `NEXT_PUBLIC_CONTRACT_ADDRESS` | `frontend/.env.example` (see §4) / Vercel env var (prod) |

```bash
# Backend — local dev
cd backend
cp .env.example .env
# then edit .env:
#   CONTRACT_ADDRESS=0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7
#   GENLAYER_NETWORK=studionet

# Backend — Fly.io (see §3's `fly secrets set`)

# Frontend — local dev (see §4)
cd frontend
cp .env.example .env.local
# then edit .env.local:
#   NEXT_PUBLIC_CONTRACT_ADDRESS=0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7

# Frontend — Vercel (Project Settings -> Environment Variables):
#   NEXT_PUBLIC_CONTRACT_ADDRESS = 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7
```

The frontend variable is prefixed `NEXT_PUBLIC_` deliberately — it's a
public contract address, safe to ship to the browser bundle (unlike
`SESSION_SECRET`/`DATABASE_URL`, which stay server-only).

---

## 3. Backend deploy (Fly.io)

**Status: complete and locally verified** (see
`backend/DEPLOYMENT_BACKEND.md`, folded in below — that file remains the
canonical backend-only copy; nothing here should ever drift from it).

**You run `fly deploy` yourself**, from your own Fly account.

### Prerequisites

- Fly CLI installed and authenticated (`fly auth whoami` to confirm).
- A Postgres instance reachable from Fly (see §5).
- The contract deployed per §1, with its address in hand.

### One-time setup

```bash
cd backend
fly launch --no-deploy   # creates the app from fly.toml, does NOT deploy yet
                          # rename `app = "covenant-watch-backend"` in
                          # fly.toml first if that name is taken

fly secrets set \
  DATABASE_URL="postgresql+psycopg://<user>:<pass>@<host>:5432/<db>" \
  SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  CONTRACT_ADDRESS="0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7" \
  GENLAYER_NETWORK="studionet" \
  CORS_ALLOWED_ORIGINS="https://<your-frontend>.vercel.app" \
  COOKIE_DOMAIN="<your-api-domain-or-leave-unset-for-apex>" \
  SENTRY_DSN=""   # optional, leave empty for the safe no-op path
```

### Deploy

```bash
fly deploy
```

`fly.toml`'s `[deploy].release_command = "alembic upgrade head"` runs
migrations automatically before the new machine takes traffic. The
`[http_service]` block sets `min_machines_running = 1` and
`auto_stop_machines = false` — this is a 24/7 always-on service (not
scale-to-zero), with an HTTP health check against `/healthz` gating
rollout.

### What was verified locally this session (not just written)

- `alembic upgrade head` applied cleanly against a real local Postgres 16
  instance (Homebrew, not Docker — Docker Desktop's daemon was not running
  in that sandbox; `docker-compose.yml`/`Dockerfile` are written and
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
  contract** at `0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7` on StudioNet
  — `get_loan_count()` returned `0` (no loans created on it yet at the
  time), which is the correct, non-fabricated result.

---

## 4. Frontend deploy (Vercel)

**Status: complete.** `frontend/` is a real Next.js 16 (App Router) +
TypeScript + Tailwind app, wired to `genlayer-js` for every contract
read/write and to the backend REST API (§3) as a read cache for
history/profile views only. `npm run build` and `npm run lint` both pass
clean (verified in this session). See `memory.md` for exactly what was and
wasn't smoke-testable in this sandbox (no real browser wallet extension to
click through a signed transaction with).

```bash
cd frontend
npm install
cp .env.example .env.local
# edit .env.local — see the full variable table below
npm run build   # verify it builds locally before deploying

# You run this yourself, from your own Vercel account:
vercel --prod
```

In the Vercel dashboard (Project Settings -> Environment Variables), set
for the Production environment:

```
NEXT_PUBLIC_CONTRACT_ADDRESS      = 0x601D14Fd4e99989883eeCC6a61dB6F0755AdF9a7
NEXT_PUBLIC_GENLAYER_NETWORK      = studionet
NEXT_PUBLIC_BACKEND_URL           = https://<your-backend>.fly.dev
NEXT_PUBLIC_GENLAYER_EXPLORER_URL = https://explorer-studio.genlayer.com/
NEXT_PUBLIC_REOWN_PROJECT_ID      = 7fe6800bb991ac35adf13217ea901615
```

`NEXT_PUBLIC_REOWN_PROJECT_ID` is the Reown (WalletConnect) AppKit project
id used for the actual connect-wallet UI (`src/lib/appkit.ts`) — get your
own at https://dashboard.reown.com if you want a project you administer;
the value above is what this session was given and is wired as the
default. All `NEXT_PUBLIC_*` variables are safe to ship to the browser
bundle by design (unlike backend's `SESSION_SECRET`/`DATABASE_URL`, which
stay server-only) — this is a public contract address, network name, API
base URL, explorer URL, and WalletConnect project id, nothing secret.

Also set the backend's CORS allowlist (`backend/app/core/config.py` /
`CORS_ORIGINS` env var) to include your Vercel production URL, or
`/auth/*` requests from the deployed frontend will be blocked by the
browser.

### What wallet connection actually is

Reown AppKit (`@reown/appkit` + `@reown/appkit-adapter-wagmi`, backed by
`wagmi`/`viem`) provides the connect-wallet modal and the EIP-1193 provider
for whatever wallet the user picks (MetaMask, WalletConnect-compatible
mobile wallets, Coinbase Wallet, etc.), configured against a real
`CaipNetwork` built from the exact `genlayer-js` `chains.studionet`
definition (`src/lib/appkit.ts`) — verified in this session by opening the
modal in a live dev server and confirming it lists real wallet options.
**Connecting a wallet is not authentication.** Every session still goes
through the real SIWE nonce/verify round trip against the backend
(`src/context/WalletContext.tsx`'s `signInWithEthereum`): `POST
/auth/nonce` -> `personal_sign` via the AppKit-connected wallet's own
provider -> `POST /auth/verify` -> httpOnly session cookie. The header's
"Connect wallet" -> "Sign in" two-step reflects this directly in the UI.

### What was verified in this sandbox vs. what needs a real wallet

- `next build` and `next lint` both pass clean.
- A live dev server was opened in-browser: the landing page, `/loans/new`
  (full covenant-builder form), and the Reown AppKit connect modal (listing
  real wallets — Trust Wallet, MetaMask, Binance Wallet, SafePal, etc.) all
  rendered correctly with no React/render console errors (only expected
  `ERR_CONNECTION_REFUSED` from the backend not running in that check).
- **Not smoke-tested end-to-end**: actually approving a `personal_sign`
  request and a real `writeContract` transaction (e.g. `create_loan`)
  through a live wallet extension — this sandbox has no real browser
  wallet to click through. The code paths are real (genlayer-js
  `writeContract`/`waitForTransactionReceipt`, no mocked signer, no
  simulated tx hash) — this is a sandbox capability gap, not a shortcut
  taken in the code. After deploying, walk the Human Verification
  Checklist below with a real wallet.

---

## 5. Postgres provisioning on Fly

Either a Fly Postgres app or any external managed Postgres works — the
backend only needs a plain `DATABASE_URL` (see
`backend/app/core/config.py`).

### Option A — Fly Postgres

```bash
fly postgres create --name covenant-watch-db --region <same-region-as-backend>
fly postgres attach covenant-watch-db --app covenant-watch-backend
# `fly postgres attach` sets DATABASE_URL as a Fly secret on the backend
# app automatically — confirm with:
fly secrets list --app covenant-watch-backend
```

### Option B — external managed Postgres (Neon / Supabase / RDS)

Create the database there, then:

```bash
fly secrets set --app covenant-watch-backend \
  DATABASE_URL="postgresql+psycopg://<user>:<pass>@<host>:5432/<db>?sslmode=require"
```

Either way, `fly deploy`'s `release_command = "alembic upgrade head"`
creates the schema (loans/covenants/checks/challenges/sessions/nonces/
sync_cursor/rate_limit_counters) on first deploy — no manual `psql`
migration step needed.

---

## 6. Post-deploy verification checklist

Mirrors JUDGE.md's Human Verification Checklist — run through this
yourself before submitting for review, so you catch anything an AI judge
would also catch.

- [ ] **Live app loads.** `https://<your-frontend>.vercel.app` renders
      without a blank page or console error on first load.
- [ ] **Main flow is usable end-to-end.** Create a loan, lock collateral,
      trigger a covenant check, see a result — as a human clicking
      through the UI, not just via curl.
- [ ] **Wallet connection works.** Connecting a real wallet (not a
      pre-filled dev account) succeeds and the app recognizes the
      connected address.
- [ ] **Correct network is used.** The frontend/backend are pointed at
      the same network the contract is actually deployed to
      (`GENLAYER_NETWORK` / `NEXT_PUBLIC_CONTRACT_ADDRESS` agree — check
      both, a mismatch here is the single most common "it doesn't work"
      bug).
- [ ] **The main flow reaches the actual contract**, not a mock or a
      hardcoded fixture. Confirm a transaction you submit from the UI
      shows up via `genlayer receipt --stdout --stderr <tx-hash>` against
      the real deployed address, and that `/healthz`'s indexer state
      reflects real on-chain data (`get_loan_count()` increasing as you
      create loans through the UI).
- [ ] **Transaction lifecycle is understandable.** The UI shows pending
      -> accepted -> finalized states (or an equivalent), not just a
      spinner that either silently succeeds or hangs forever.
- [ ] **Errors are understandable.** A rejected transaction (e.g. wrong
      collateral amount, cooldown active) surfaces a human-readable
      message in the UI, not a raw stack trace or a silent no-op.
- [ ] **Contract address is correct everywhere.** The address shown in
      the UI (if displayed), the backend's `CONTRACT_ADDRESS`, and the
      frontend's `NEXT_PUBLIC_CONTRACT_ADDRESS` are all the exact same
      address you deployed in §1 — copy-paste, don't retype.
- [ ] **Deployed methods correspond to the submitted source.** Run
      `genlayer schema` (§1) again against the live address and diff its
      method list against `contracts/covenant_watch.py`'s
      `@gl.public.write`/`@gl.public.view` methods — they must match
      exactly. If you've redeployed since editing the contract, make sure
      the address everywhere is the NEW one.
- [ ] **No mock/simulated integration.** Every covenant check a judge
      triggers through the live UI performs a real `gl.nondet.web.render`
      / `gl.nondet.exec_prompt` / `gl.get_contract_at` call on-chain — not
      a canned response. `tests/integration/` (see `memory.md`) is the
      evidence trail that these real paths were exercised and what their
      actual results were; it is not a substitute for checking the live
      deployment yourself here.

---

## Appendix: file map

| Concern | File |
|---|---|
| Contract | `contracts/covenant_watch.py` |
| Direct (mocked, fast) tests | `tests/direct/` |
| Integration (real network) tests | `tests/integration/` |
| Backend-only deploy notes | `backend/DEPLOYMENT_BACKEND.md` |
| Backend env template | `backend/.env.example` |
| Frontend env template | `frontend/.env.example` |
| Full project status | `memory.md` |
