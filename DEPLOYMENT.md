# Covenant Watch deployment runbook

Last verified: 13 October 2026.

## Current production configuration

| Component | Value |
|---|---|
| GenLayer StudioNet adjudicator | `0x1EC71Df45C68F9F52A155DbBC8def172B00819C4` |
| GenLayer deployment transaction | `0x375f98f42157f8e3cf941074036f2d26cc140c3fae02b3a1233d630fbca60ffa` |
| Base Sepolia escrow | `0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2` |
| Base deployment transaction | `0x3ffd97e520394dc4577420b3df987711bb857f8a305e7868fc6674075dfd8dfb` |
| Base owner/deployer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Dedicated Base relayer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Relayer funding transaction | `0xd2088bc32f7cf7143b0e5f44060fc2e0eacdb55fa58264e50d885b031bfdec34` |
| Circle Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Frontend | https://covenant-watch.vercel.app |
| Vercel deployment | `dpl_BG3fddp9AQWHYgTYFpESUZ8fJJ8J` |
| Backend | https://covenant-watch-api.fly.dev |
| Fly app / region | `covenant-watch-api` / `iad` |

The GenLayer deployment is finalized and successful with five agreeing validators. The live acceptance run created three paired loans, and the production backend indexes those three loans.

## 1. Verify source locally

```bash
forge test -vv
backend/.venv/bin/pytest -q backend/tests
cd frontend && npm run lint && npx tsc --noEmit && npm run build -- --webpack
```

These are local checks. Do not describe them as live-chain E2E evidence.

## 2. Deploy Base Sepolia

```bash
forge build
forge create contracts/base/CovenantWatchEscrow.sol:CovenantWatchEscrow \
  --rpc-url "$BASE_SEPOLIA_RPC_URL" --private-key "$DEPLOYER_PRIVATE_KEY" \
  --broadcast --constructor-args \
  0x036CbD53842c5426634e7929541eC2318f3dCF7e "$RELAYER_ADDRESS"
```

Record the address and receipt, then read `owner`, `relayer`, `usdc`, and `loanCount` directly. The constructor must point to Circle's Base Sepolia USDC and a dedicated relayer address.

## 3. Deploy GenLayer StudioNet

```bash
genlayer config set network=studionet
genlayer deploy --contract contracts/covenant_watch.py
genlayer receipt <transaction-hash>
genlayer call <contract-address> get_loan_count
```

Do not wire the address until the deployment receipt is `FINALIZED` and execution is successful. The deployed ABI must match the checked-in contract. `create_loan` takes borrower, principal, collateral, interest, maturity, covenants JSON, and an optional challenge window; it does not accept native value.

## 4. Configure services

Backend production secrets/configuration:

```text
CONTRACT_ADDRESS=0x1EC71Df45C68F9F52A155DbBC8def172B00819C4
GENLAYER_NETWORK=studionet
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
BASE_ESCROW_ADDRESS=0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2
BASE_RELAYER_PRIVATE_KEY=<Fly secret; never commit>
```

Frontend build variables:

```text
NEXT_PUBLIC_CONTRACT_ADDRESS=0x1EC71Df45C68F9F52A155DbBC8def172B00819C4
NEXT_PUBLIC_GENLAYER_NETWORK=studionet
NEXT_PUBLIC_BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
NEXT_PUBLIC_BASE_ESCROW_ADDRESS=0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2
NEXT_PUBLIC_BACKEND_URL=https://covenant-watch-api.fly.dev
NEXT_PUBLIC_GENLAYER_EXPLORER_URL=https://explorer-studio.genlayer.com/
```

Deploy with `fly deploy -a covenant-watch-api` from `backend/` and `vercel --prod --yes` from `frontend/`. Verify `/healthz`, `/loans`, and `/settings`. Address changes require a backend restart and a new frontend build.

## 5. Acceptance flow

The browser uses the exact EIP-6963 provider chosen by the user. Origination must request Base Sepolia for USDC approval and principal escrow, then GenLayer StudioNet for adjudication registration. Borrower activation requests Base for approval/staking and then GenLayer to record the confirmed Base hash.

For live acceptance, verify every receipt in its explorer and confirm actual USDC balance changes on Base. GenLayer `ACCEPTED` is not finality; wait for `FINALIZED` and successful execution. The remediation runner is `tests/e2e/security_acceptance.py`; the completed evidence artifact contains Base receipts, GenVM success, validator votes, state readbacks, and USDC balance deltas.

## 6. Relay operation

The indexer considers only finalized GenLayer checks. It maps the outcome to the Base enum, submits `applyDecision`, waits for the Base receipt, and records the Base hash with `mark_decision_relayed`. Base enforces relayer authorization and per-check replay protection. Retry a failed relay only after checking chain state; never resubmit a confirmed relay.

## 7. Rollback

Contracts are immutable. Rollback means restoring a compatible pair of Base and GenLayer addresses in both services. Never mix counters from unrelated deployments: loan IDs are paired by synchronized origination. Restart Fly and rebuild Vercel, then verify read-only state before allowing writes.
