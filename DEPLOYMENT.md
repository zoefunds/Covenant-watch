# Covenant Watch deployment runbook

Last verified: 13 October 2026.

## Current deployment

| Component | Value |
|---|---|
| GenLayer StudioNet adjudicator | `0xa49283a086fE5122Cf3967b6ADb50A50fA736905` |
| GenLayer deploy tx | `0x37f1509f624da25dd0739b0d6999529d8bcd57b8adc06828a0c2cfa9ade41405` |
| Base Sepolia escrow | `0x8D9cc4Efd412cEd3c10de543a46b8390CAa8ADe7` |
| Base deploy tx | `0xfa10de0df52a3d569fb956fa1e3ee75238c78f957574f627132ee31ad939ebfe` |
| Dedicated Base relayer | `0x35F5ea45122eE7Dd5Ec6aA6aab961E9147e3e9e8` |
| Relayer rotation tx | `0xa5429e4fed4b141895c00e49eeb4e31f79dc7345db12bce068a36cfcd0f635ae` |
| Relayer funding tx | `0xd2088bc32f7cf7143b0e5f44060fc2e0eacdb55fa58264e50d885b031bfdec34` |
| Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Frontend | https://covenant-watch.vercel.app |
| Backend | https://covenant-watch-api.fly.dev |

## Verify source

```bash
forge test -vv
backend/.venv/bin/pytest -q backend/tests
cd frontend && npm run lint && npx tsc --noEmit && npm run build -- --webpack
```

## Deploy Base Sepolia

```bash
forge build
forge create contracts/base/CovenantWatchEscrow.sol:CovenantWatchEscrow \
  --rpc-url "$BASE_SEPOLIA_RPC_URL" --private-key "$DEPLOYER_PRIVATE_KEY" \
  --broadcast --constructor-args \
  0x036CbD53842c5426634e7929541eC2318f3dCF7e "$RELAYER_ADDRESS"
```

Record the address and transaction. Confirm `owner`, `relayer`, and `usdc`
before wiring the application. The relayer should be a dedicated testnet wallet.

## Deploy GenLayer

```bash
genlayer network set studionet
genlayer deploy --contract contracts/covenant_watch.py
genlayer receipt --status FINALIZED <transaction-hash>
genlayer call <contract-address> get_loan_count
```

Require a successful finalized receipt. This contract is adjudication-only:
its schema must not expose payable loan, collateral, repayment, or claim calls.

## Configure services

Backend secrets/configuration:

```text
CONTRACT_ADDRESS=<GenLayer address>
GENLAYER_NETWORK=studionet
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
BASE_ESCROW_ADDRESS=<Base address>
BASE_RELAYER_PRIVATE_KEY=<secret>
```

Frontend build variables:

```text
NEXT_PUBLIC_CONTRACT_ADDRESS=<GenLayer address>
NEXT_PUBLIC_GENLAYER_NETWORK=studionet
NEXT_PUBLIC_BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
NEXT_PUBLIC_BASE_ESCROW_ADDRESS=<Base address>
NEXT_PUBLIC_BACKEND_URL=https://covenant-watch-api.fly.dev
```

Deploy backend with `fly deploy -a covenant-watch-api` and frontend with
`vercel --prod --yes`. Verify `/healthz`, `/settings`, `/loans`, and
`/milestone` after rollout.

## Live E2E evidence

The authorized live runner is `tests/e2e/base_live.py`. It requires the
throwaway deployer key only through `DEPLOYER_PRIVATE_KEY`; never write the key
to a file. `tests/e2e/report_live.py` reads confirmed event logs and regenerates
`frontend/src/data/milestoneScenarios.json` without a key.

## Relay requirements

Only relay a GenLayer check after it is finalized. Translate status as
`Compliant=0`, `Breach=1`, `Inconclusive=2`, and use the covenant's immutable
step-up/seizure parameters. Submit once with `applyDecision`; after the Base
receipt confirms, record its transaction hash through
`mark_decision_relayed`. A Base retry is safe because `(loanId, checkId)` is
replay-protected.

## Rollback

Contracts are immutable. Rollback means restoring both prior addresses in the
backend and frontend together. Never mix counters from unrelated Base and
GenLayer deployments; loan IDs are paired by synchronized fresh deployments.
