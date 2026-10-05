# Covenant Watch Deployment Runbook

Last verified: 2026-10-05.

## Current production

| Component | Value |
|---|---|
| Network | GenLayer StudioNet |
| Contract | `0x5c3Fe893aaaa9C0416F76812c3903Cf4AfA528A7` |
| Contract deploy tx | `0x7846dfbfac2d37fd5b2b3938f3620df1cb3e6650193ef5e1e4326e7aadc1a039` |
| Frontend | https://covenant-watch.vercel.app |
| Vercel project | `covenant-watch` |
| Backend | https://covenant-watch-api.fly.dev |
| Fly app | `covenant-watch-api` |

The deploy transaction is `FINALIZED`; its five validators all voted `AGREE`.

## 1. Verify source before deployment

```bash
gltest tests/direct/ -v
cd backend && .venv/bin/pytest -q && cd ..
cd frontend && npm run lint && npx tsc --noEmit && npm run build -- --webpack && cd ..
git diff --check
```

Expected baseline: 37 contract tests and 17 backend tests pass. The webpack
build currently emits non-fatal optional Reown/Wagmi connector-resolution
warnings but must complete and emit every route.

## 2. Deploy the Intelligent Contract

The commands below match the installed `genlayer` CLI:

```bash
genlayer network set studionet
genlayer account list
genlayer deploy --contract contracts/covenant_watch.py
```

Record both the transaction hash and new address. Wait for actual finality:

```bash
genlayer receipt --status FINALIZED <deploy-tx-hash>
genlayer schema <contract-address>
genlayer code <contract-address>
genlayer call <contract-address> get_loan_count
```

The schema must expose 21 public methods: 11 writes and 10 views. The installed
CLI does not expose payable call value on `genlayer write`, so use the included
Node harness—not a value-less CLI write—to test escrow.

## 3. Run the real payable, LLM-backed lifecycle

`tests/integration/live_studionet.mjs` uses unlocked test accounts and
`genlayer-js` to submit native values. It waits for `FINALIZED`, requires
successful execution, dynamically resolves loan/covenant/check IDs, and can
resume an existing loan without blindly duplicating writes.

The evidence set that passed 3/3 on StudioNet was:

- `https://en.wikipedia.org/wiki/Bitcoin`
- `https://river.com/learn/terms/1/21-million/`
- `https://www.fidelitydigitalassets.com/research-and-insights/understanding-bitcoin-and-ethereum-supply`

Example:

```bash
CONTRACT_ADDRESS='<contract-address>' \
SOURCE_URLS='https://en.wikipedia.org/wiki/Bitcoin,https://river.com/learn/terms/1/21-million/,https://www.fidelitydigitalassets.com/research-and-insights/understanding-bitcoin-and-ethereum-supply' \
CONDITION_FIELD=max_bitcoin_supply \
OPERATOR='==' \
THRESHOLD=21000000 \
COVENANT_DESCRIPTION='Independent publishers must corroborate Bitcoin maximum supply as 21,000,000.' \
node tests/integration/live_studionet.mjs
```

If direct Node/Python TLS calls to StudioNet fail with
`SSL/TLS_ALERT_BAD_RECORD_MAC`, start
`tests/integration/rpc_curl_proxy.py` and set
`GENLAYER_RPC_URL=http://127.0.0.1:4133`. Stop the local proxy afterward.

Success must include a finalized `COMPLIANT` check, 2/3 or 3/3 publisher
quorum, genuine validator agreement, terminal `REPAID`, and zero remaining
claimable balances. The verified production run achieved 3/3 publisher
corroboration on loan `2` with observed value `21000000.000000`.

Avoid using cryptocurrency JSON API endpoints as evidence until the current
GenVM renderer issue is resolved. One live attempt crashed in the GenVM host
before validator selection (`INTERNAL_ERROR`, `NO_MAJORITY`, zero validators).
Document pages completed successfully. Such a host crash is not a covenant
verdict and must never be shown as success.

## 4. Wire the address

Keep these values identical:

- backend local/production: `CONTRACT_ADDRESS`
- frontend local/production: `NEXT_PUBLIC_CONTRACT_ADDRESS`
- frontend public fallback in `frontend/src/lib/config.ts`
- `.env.example`, `README.md`, `AUDIT.md`, and `memory.md`

After a new contract deployment, update the files with normal reviewable edits
and run the complete verification baseline again.

## 5. Deploy backend

Set the address first; this restarts the machine:

```bash
fly secrets set \
  CONTRACT_ADDRESS='<contract-address>' \
  GENLAYER_NETWORK=studionet \
  -a covenant-watch-api
```

Deploy whenever backend source, requirements, Alembic migrations, Dockerfile,
or `fly.toml` changed:

```bash
cd backend
fly deploy -a covenant-watch-api
```

`fly.toml` runs `alembic upgrade head` before its rolling update. Verify:

```bash
curl https://covenant-watch-api.fly.dev/healthz
fly status -a covenant-watch-api
```

Require `status: ok`, `database: ok`, `contract_configured: true`, indexer
`idle`/`syncing`, a populated `last_success_at`, and `last_error: null`.

## 6. Deploy frontend

```bash
cd frontend
vercel --prod --yes \
  --build-env NEXT_PUBLIC_CONTRACT_ADDRESS='<contract-address>' \
  --env NEXT_PUBLIC_CONTRACT_ADDRESS='<contract-address>'
```

Production also uses:

```text
NEXT_PUBLIC_GENLAYER_NETWORK=studionet
NEXT_PUBLIC_BACKEND_URL=https://covenant-watch-api.fly.dev
NEXT_PUBLIC_GENLAYER_EXPLORER_URL=https://explorer-studio.genlayer.com/
NEXT_PUBLIC_REOWN_PROJECT_ID=<your-public-Reown-project-id>
```

Verify the deployment reaches `READY` and is aliased to
`https://covenant-watch.vercel.app`.

## 7. Post-deployment checks

- Load the production frontend and inspect the settings page values.
- Connect a real wallet and complete SIWE authentication.
- Confirm every write displays submitted/pending status and does not update
  application state at `ACCEPTED`; it must wait for `FINALIZED` plus successful
  execution.
- Confirm a finalized action immediately rereads contract state and disables a
  one-shot button that is no longer valid.
- Check maturity, grace, challenge, and cooldown countdowns against
  `get_current_time`/contract view results.
- Create a three-publisher covenant and confirm distinct-host validation.
- Resolve transaction status and on-chain state before retrying any interrupted
  write; use `RESUME_LOAN_ID` in the live harness where applicable.
- Verify backend health and that its cache eventually reflects the new loan,
  while direct chain state remains authoritative.

## 8. Rollback and incident handling

Contracts are immutable deployments. Rollback means restoring the prior
address in Vercel/Fly and redeploying/restarting those services; it does not
rewrite existing loans. Never point an existing UI at a contract whose schema
does not match `frontend/src/lib/contract.ts`.

For a GenVM error, inspect the exact transaction receipt. Distinguish a host
`INTERNAL_ERROR`/`NO_MAJORITY` from an on-chain `INCONCLUSIVE` verdict and from
a deterministic contract revert. Only a finalized successful receipt may drive
the UI's success state.

See `AUDIT.md`, `memory.md`, `backend/README.md`, and `frontend/README.md` for
the current security model and component details.
