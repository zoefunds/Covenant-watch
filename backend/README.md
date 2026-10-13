# Covenant Watch backend

FastAPI, PostgreSQL, Redis, and an indexer/decision relayer for Covenant Watch. Production is `https://covenant-watch-api.fly.dev` (`covenant-watch-api`, Fly region `iad`).

## Authority boundary

The backend is non-custodial for user actions. Users approve USDC, create and fund loans, stake collateral, draw principal, repay, and claim directly from their browser wallets. The backend has one narrow funded role: it submits finalized GenLayer decisions to the configured Base escrow through `applyDecision`. Base independently checks the relayer address and rejects repeated `(loanId, checkId)` decisions.

The service provides:

- a rebuildable PostgreSQL cache for loan lists, profiles, and history;
- direct Base state enrichment for paired loans;
- SIWE-style nonce verification and signed session cookies;
- an SSRF-protected informational URL preview;
- GenLayer RPC budgeting and indexer health;
- finalized-decision relay from GenLayer to Base Sepolia.

Cached data must not decide whether a money-moving action is valid. The Base and GenLayer contracts enforce their respective state machines.

## Indexing and relay

`app/workers/indexer.py` polls the configured GenLayer contract and scopes rows to that address. Passes are serialized with an in-process lock and a PostgreSQL advisory lock. A timed-out synchronous RPC worker retains its lease until it exits, preventing replacement-thread accumulation.

After indexing, the worker finds finalized, unrelayed checks. It verifies Base replay state, submits the mapped decision with `app/services/base_sepolia.py`, requires a successful Base receipt, and records the Base transaction hash on GenLayer. If relay configuration is absent, indexing continues without writes.

The production poll interval is 300 seconds, so a finalized transaction may appear onchain before cached list/history routes update.

## Authentication

1. `POST /auth/nonce` creates a single-use nonce with a five-minute TTL.
2. The selected browser wallet signs the returned message.
3. `POST /auth/verify` recovers and checks the signer, consumes the nonce, creates a session, and sets a signed httpOnly cookie (`Secure` in production, `SameSite=strict`).
4. Protected routes resolve that cookie; a request-body address is never sufficient.

Wallet connection and backend authentication are separate states.

## URL preview

`POST /covenants/preview-source` is creation-time assistance only. It resolves DNS and blocks private, loopback, link-local, reserved, and metadata destinations through redirects. Preview output never becomes a covenant verdict; GenLayer validators fetch the immutable source set independently.

## RPC budget and rate limiting

GenLayer reads use `call_contract_view_budgeted`. Redis coordinates a fixed-window budget and SlowAPI rate limits across instances. Request-time budget exhaustion returns HTTP 503 with `Retry-After`; the indexer pauses its pass. Redis coordination failure is logged and fails open so an auxiliary outage does not take down the API.

## Configuration

Copy `.env.example` to `.env`. Current public values are:

```text
CONTRACT_ADDRESS=0xb86d1525014c80F98E7f0C3Be2af60AF3ab761F8
GENLAYER_NETWORK=studionet
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
BASE_ESCROW_ADDRESS=0x6b806484E938E8Bf5eD65D1841543931240834ef
BASE_RELAYER_PRIVATE_KEY=<secret; backend only>
```

Also configure PostgreSQL `DATABASE_URL`, Redis `REDIS_URL`, a random `SESSION_SECRET`, and the allowed frontend origin. Settings are process-cached; restart after changing either contract address.

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

`docker compose up --build` is the packaged alternative. Do not put a production or funded relayer key in a local file.

## Current production state

On 13 October 2026, Fly was configured with the fresh Base and GenLayer addresses. Health checks succeeded and `/loans` returned `[]`, consistent with both contracts reporting zero loans. No live E2E loan has been run against this address pair.
