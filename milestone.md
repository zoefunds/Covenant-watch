# Covenant Watch milestone — Base Sepolia USDC + GenLayer adjudication

Completed 13 October 2026.

## Delivered architecture

- **Base Sepolia is the value layer.** `CovenantWatchEscrow.sol` holds Circle test USDC, escrows principal, stakes collateral, accepts repayment, creates pull-based claims, and applies finalized breach consequences.
- **GenLayer is adjudication only.** `covenant_watch.py` stores covenant definitions, independently evaluates pinned public sources with validator consensus, accepts additive challenge evidence, and finalizes results. It has no payable write and no outbound transfer primitive.
- **The relay is narrow and replay-safe.** The backend submits `(loanId, checkId, decision, tier1StepBps, tier2SeizureBps)` to Base. Only the configured relayer is accepted, and repeated `(loanId, checkId)` submissions revert.

This follows the Meme Olympics chain split, adapted to Covenant Watch's loan state machine.

## Live deployments

| Component | Address / transaction |
|---|---|
| Base Sepolia escrow | `0x8D9cc4Efd412cEd3c10de543a46b8390CAa8ADe7` |
| Base deployment tx | `0xfa10de0df52a3d569fb956fa1e3ee75238c78f957574f627132ee31ad939ebfe` |
| Dedicated Base relayer | `0x35F5ea45122eE7Dd5Ec6aA6aab961E9147e3e9e8` |
| Relayer rotation tx | `0xa5429e4fed4b141895c00e49eeb4e31f79dc7345db12bce068a36cfcd0f635ae` |
| Relayer funding tx | `0xd2088bc32f7cf7143b0e5f44060fc2e0eacdb55fa58264e50d885b031bfdec34` |
| Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| GenLayer adjudicator | `0xa49283a086fE5122Cf3967b6ADb50A50fA736905` |
| GenLayer deployment tx | `0x37f1509f624da25dd0739b0d6999529d8bcd57b8adc06828a0c2cfa9ade41405` |

The GenLayer deployment reached `FINALIZED`, executed successfully, and received three `AGREE` validator votes in one round.

## Implementation

The Base contract provides `createLoan`, `stakeCollateral`, `applyDecision`, `claimPrincipal`, exact `repay`, maturity settlement, cancellation, and pull-based `claimSettlement`. Principal remains locked until the required number of unique compliant GenLayer decisions have been relayed. It includes non-reentrancy, checks-effects-interactions, an immutable USDC address, a rotatable relayer, and per-check replay protection.

Native GEN escrow and all payout functions were removed from GenLayer. `create_loan` records six-decimal USDC terms without call value. `activate_base_loan` and `mark_decision_relayed` store Base transaction hashes only. Evidence fetching, structured validator equivalence, challenges, and finalization remain on GenLayer.

Backend configuration now includes Base RPC, escrow, USDC, and relayer settings. `base_sepolia.py` supplies authoritative Base reads and the sole decision-relay write; `GET /loans/{id}/base` exposes live payment state.

The frontend now originates via USDC approval + Base escrow creation before registering covenant terms on GenLayer. Collateral, draw, repayment, and settlement use Base; checks and challenges use GenLayer. Monetary labels use six-decimal USDC. `/loans` renders the checked-in live test loans with BaseScan links.

## Three live end-to-end scenarios

Full event hashes and final state live in `frontend/src/data/milestoneScenarios.json`.

1. **Compliant repayment (loan 0):** 10 USDC principal and 15 USDC collateral; compliant decision, borrower draw, exact 10.5 USDC repayment, and both settlement claims. Final: `Repaid`, zero escrow and claimables.
2. **Graduated breach (loan 1):** the first breach raised interest from 5% to 7%; the second allocated 3.75 USDC (25%) to the lender and left 11.25 USDC staked. Final: `Tier 2`.
3. **Tier-3 default (loan 2):** three unique decision IDs produced terminal default; remaining collateral plus undrawn principal were allocated and claimed by the lender. Final: `Defaulted`, zero stranded funds.

The matching Foundry suite passes 3/3. Backend tests pass 17/17, the Solidity build succeeds, and the Next.js production build completes.

## Operations and security

- The supplied wallet was used only as the throwaway testnet deployer and to authorize the dedicated relayer. Its private key is not committed or stored by the application.
- Fly stores a separate randomly generated `BASE_RELAYER_PRIVATE_KEY` as an encrypted production secret. Only its public address is documented.
- Base and GenLayer loan IDs are synchronized from fresh deployments.
- Relay only after GenLayer finality. Failed submissions may retry; successful submissions are rejected on replay.

## Verification

```bash
forge test -vv
backend/.venv/bin/pytest -q backend/tests
cd frontend && npm run lint && npx tsc --noEmit && npm run build -- --webpack
```
