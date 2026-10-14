# Covenant Watch deployment runbook

Last verified: 13 October 2026.

## Current production configuration

| Component | Value |
|---|---|
| GenLayer StudioNet adjudicator | `0x1b4BA5Fe8894648E4B90d80f2DA5d53880CcfD7b` |
| GenLayer deployment transaction | `0x9698a8fa9f6db79cbcda2a0986243d4b60f0f993003049864bdccf7f0aa0634a` |
| Base Sepolia escrow | `0xbF8F70Db480d003Dd6c5629c50b1f9Bf3Adc9E9b` |
| Base deployment transaction | `0x1690edbcf6b5a519ac5c574235579e88a966185f3596251dffc33691b6e9df68` |
| Base owner/deployer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Dedicated Base relayer | `0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A` |
| Decision signer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
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

Record the address and receipt, then read `owner`, `relayer`, `decisionSigner`, `genLayerContract`, `usdc`, and `loanCount` directly. The constructor must point to Circle's Base Sepolia USDC, the dedicated relayer and signer, and the exact GenLayer deployment used in the attestation domain.

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
CONTRACT_ADDRESS=0x1b4BA5Fe8894648E4B90d80f2DA5d53880CcfD7b
GENLAYER_NETWORK=studionet
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
BASE_ESCROW_ADDRESS=0xbF8F70Db480d003Dd6c5629c50b1f9Bf3Adc9E9b
BASE_RELAYER_PRIVATE_KEY=<Fly secret; never commit>
```

Frontend build variables:

```text
NEXT_PUBLIC_CONTRACT_ADDRESS=0x1b4BA5Fe8894648E4B90d80f2DA5d53880CcfD7b
NEXT_PUBLIC_GENLAYER_NETWORK=studionet
NEXT_PUBLIC_BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
NEXT_PUBLIC_BASE_ESCROW_ADDRESS=0xbF8F70Db480d003Dd6c5629c50b1f9Bf3Adc9E9b
NEXT_PUBLIC_BACKEND_URL=https://covenant-watch-api.fly.dev
NEXT_PUBLIC_GENLAYER_EXPLORER_URL=https://explorer-studio.genlayer.com/
```

Deploy with `fly deploy -a covenant-watch-api` from `backend/` and `vercel --prod --yes` from `frontend/`. Verify `/healthz`, `/loans`, and `/settings`. Address changes require a backend restart and a new frontend build.

## 5. Acceptance flow

The browser uses the exact EIP-6963 provider chosen by the user. Origination must request Base Sepolia for USDC approval and principal escrow, then GenLayer StudioNet for adjudication registration. Borrower activation requests Base for approval/staking and then GenLayer to record the confirmed Base hash.

For live acceptance, verify every receipt in its explorer and confirm actual USDC balance changes on Base. GenLayer `ACCEPTED` is not finality; wait for `FINALIZED` and successful execution. The remediation runner is `tests/e2e/security_acceptance.py`; the completed evidence artifact contains Base receipts, GenVM success, validator votes, state readbacks, and USDC balance deltas.

## 6. Relay operation

The indexer considers only finalized GenLayer checks. It maps the outcome to the Base enum, signs the contract/chain/GenLayer/loan/check/covenant/decision/commitment/deadline payload, submits `applyDecision`, waits for the Base receipt, and records the Base hash with `mark_decision_relayed`. Base enforces relayer authorization, signer recovery, expiry, frozen commitments, and per-check replay protection. Retry a failed relay only after checking chain state; never resubmit a confirmed relay.

## 7. Rollback

Contracts are immutable. Rollback means restoring a compatible pair of Base and GenLayer addresses in both services. Never mix counters from unrelated deployments: loan IDs are paired by synchronized origination. Restart Fly and rebuild Vercel, then verify read-only state before allowing writes.
