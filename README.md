# Covenant Watch

> Write the promise into the loan. Let the public record decide if it was broken.

Covenant Watch is a two-chain covenant-monitoring loan protocol. Base Sepolia is the economic layer: it holds Circle test USDC for principal, collateral, repayment, and settlement. GenLayer StudioNet is the adjudication layer: its validators evaluate immutable covenant evidence and finalize a decision that a dedicated backend relayer submits to Base.

## Current deployment

Last verified: 13 October 2026.

| Component | Current value |
|---|---|
| Frontend | https://covenant-watch.vercel.app |
| Backend | https://covenant-watch-api.fly.dev |
| GenLayer adjudicator | `0xb86d1525014c80F98E7f0C3Be2af60AF3ab761F8` |
| Base Sepolia escrow | `0x6b806484E938E8Bf5eD65D1841543931240834ef` |
| Circle Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Base decision relayer | `0x35F5ea45122eE7Dd5Ec6aA6aab961E9147e3e9e8` |

Both contracts were freshly deployed for this milestone and currently report zero loans. No live E2E loan was created on these addresses; acceptance testing is intentionally left to the user.

## Transaction flow

1. The lender connects a directly discovered EIP-6963 browser wallet.
2. The app switches to Base Sepolia, obtains USDC approval, and calls `createLoan`; the escrow pulls the principal from the lender.
3. The app switches the same selected wallet to GenLayer StudioNet and calls `create_loan` with the matching loan ID and covenant definitions.
4. The borrower approves USDC and calls `stakeCollateral` on Base, then records the confirmed Base transaction through `activate_base_loan` on GenLayer.
5. Covenant checks and challenges execute only on GenLayer. Finalized decisions are relayed by the backend to Base through replay-protected `applyDecision`.
6. Principal draw, exact repayment, maturity handling, and pull-based settlement claims execute only on Base Sepolia.

```text
browser wallet ── USDC approval / escrow / stake / repay / claim ──▶ Base
      │                                                               ▲
      └──── terms / checks / challenges ─────▶ GenLayer ── decision ──┘
```

There is no Reown or wagmi connector layer. The provider selected during EIP-6963 discovery is used for SIWE, Base, and GenLayer, and the app verifies the active chain after each switch.

## Authority boundaries

- `contracts/base/CovenantWatchEscrow.sol` is the only value-bearing contract.
- `contracts/covenant_watch.py` performs adjudication and never holds funds.
- The backend is a read cache, authentication service, URL-preview service, and narrow finalized-decision relayer. It cannot originate, stake, draw, repay, or claim a loan.
- The Base contract rejects an unauthorized relayer and rejects a repeated `(loanId, checkId)` decision.
- Cached API data is non-authoritative. Contracts enforce all money-relevant state transitions.

## Repository

```text
contracts/covenant_watch.py             GenLayer adjudication contract
contracts/base/CovenantWatchEscrow.sol  Base Sepolia USDC escrow
backend/                                FastAPI cache, SIWE, indexing, relay
frontend/                               Next.js browser-wallet application
test/                                   Foundry economic unit tests
tests/e2e/                              Optional live paired-chain runner
milestone.md                            Current milestone record
DEPLOYMENT.md                           Deployment and operations runbook
AUDIT.md                                Current security review
```

## Local verification

These checks do not submit live-chain transactions:

```bash
forge test -vv
backend/.venv/bin/pytest -q backend/tests
cd frontend
npm run lint
npx tsc --noEmit
npm run build -- --webpack
```

The `/loans` page renders indexed contract data only. No checked-in loan cards or fabricated verified-loan fixtures are shown. Configuration examples are in `backend/.env.example` and `frontend/.env.example`; keep `BASE_RELAYER_PRIVATE_KEY` only in backend secret storage.
