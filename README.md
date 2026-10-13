# Covenant Watch

> Write the promise into the loan. Let the public record decide if it was broken.

Covenant Watch is a two-chain covenant-monitoring loan protocol. Base Sepolia holds test USDC for principal, collateral staking, repayment, and settlement. GenLayer independently adjudicates whether precommitted covenants were satisfied and produces the finalized decision relayed to Base.

## Live milestone deployment

| Component | Value |
|---|---|
| Frontend | https://covenant-watch.vercel.app |
| Backend | https://covenant-watch-api.fly.dev |
| GenLayer adjudicator | `0xa49283a086fE5122Cf3967b6ADb50A50fA736905` |
| Base Sepolia escrow | `0x8a34e37A4A1Fe74848389F13033099c0Fe889472` |
| Circle Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |

See [milestone.md](./milestone.md) for deployment transactions, three live USDC E2E scenarios, final states, and the full implementation record.

## Architecture

```text
wallet ──approve / principal / collateral / repay / claim──▶ Base escrow
   │                                                          ▲
   └── covenant terms / checks / challenges ──▶ GenLayer      │
                                                  │ finalized │
                                                  └─ decision relay
```

- `contracts/base/CovenantWatchEscrow.sol` is the only value-bearing contract.
- `contracts/covenant_watch.py` is adjudication-only and has no payable entry point or outbound value-transfer primitive.
- `backend/app/services/base_sepolia.py` reads Base state and relays finalized decisions through one dedicated, replay-protected boundary.
- The browser signs user-owned Base and GenLayer transactions directly. The backend never custodies user funds.

GenLayer validators independently fetch the immutable source set, compare a structured `{status, observed_value, source_hash}` result with numeric tolerance, return `INCONCLUSIVE` rather than guessing, and accept only additive challenge evidence. A breach becomes relayable only after its challenge window closes and finalization succeeds.

The Base contract enforces the economic state machine: 1) interest step-up, 2) partial collateral seizure, 3) terminal default. Decision IDs cannot be replayed. Claims use checks-effects-interactions and a non-reentrancy guard.

## Repository

```text
contracts/covenant_watch.py             GenLayer adjudication contract
contracts/base/CovenantWatchEscrow.sol  Base Sepolia USDC contract
backend/                                FastAPI cache, SIWE, Base reader/relay
frontend/                               Next.js wallet application
test/                                   Foundry economic scenario tests
tests/e2e/                               Live Base runner and evidence exporter
milestone.md                             Milestone implementation and receipts
DEPLOYMENT.md                            Deployment and operations runbook
```

## Verification

```bash
forge test -vv
backend/.venv/bin/pytest -q backend/tests
cd frontend && npm run lint && npx tsc --noEmit && npm run build -- --webpack
```

Live evidence is checked in at `frontend/src/data/milestoneScenarios.json` and rendered at `/milestone`.

Copy `backend/.env.example` and `frontend/.env.example` for configuration. Keep `BASE_RELAYER_PRIVATE_KEY` only in backend secret storage. Full production steps are in [DEPLOYMENT.md](./DEPLOYMENT.md).
