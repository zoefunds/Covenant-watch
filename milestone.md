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
| Base Sepolia escrow | `0x5e54C6fB260DB3d6C23C547E7aF1309D7fF0054a` |
| Base deployment tx | `0xf61246967d888ff7c90e41438f8c4fa44f54c38035fb809c7502c99612aa98f9` |
| Dedicated Base relayer | `0x35F5ea45122eE7Dd5Ec6aA6aab961E9147e3e9e8` |
| Relayer funding tx | `0xd2088bc32f7cf7143b0e5f44060fc2e0eacdb55fa58264e50d885b031bfdec34` |
| Base Sepolia USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| GenLayer adjudicator | `0xA60b429D26831BB3E381b8Bba184D685b6741020` |
| GenLayer deployment tx | `0x9b8e7493e3eda53c649220b66e6b7773e2f18f58c86acf4423266efbbdebac9d` |
| GenLayer source helper | `0x78276bCCBE904b989c96a5B19B8E5820Ff0b12AA` |

The GenLayer deployment reached `FINALIZED`, executed successfully, and received three `AGREE` validator votes in one round.

## Implementation

The Base contract provides `createLoan`, `stakeCollateral`, `applyDecision`, `claimPrincipal`, exact `repay`, maturity settlement, cancellation, and pull-based `claimSettlement`. Principal remains locked until the required number of unique compliant GenLayer decisions have been relayed. It includes non-reentrancy, checks-effects-interactions, an immutable USDC address, a rotatable relayer, and per-check replay protection.

Native GEN escrow and all payout functions were removed from GenLayer. `create_loan` records six-decimal USDC terms without call value. `activate_base_loan` and `mark_decision_relayed` store Base transaction hashes only. Evidence fetching, structured validator equivalence, challenges, and finalization remain on GenLayer.

Backend configuration now includes Base RPC, escrow, USDC, and relayer settings. `base_sepolia.py` supplies authoritative Base reads and the sole decision-relay write; `GET /loans/{id}/base` exposes live payment state.

The frontend now originates via USDC approval + Base escrow creation before registering covenant terms on GenLayer. Collateral, draw, repayment, and settlement use Base; checks and challenges use GenLayer. Monetary labels use six-decimal USDC. `/loans` renders only backend-indexed GenLayer loans; the former checked-in scenario cards were removed.

## Three live end-to-end scenarios

All three scenarios exist as loan IDs 0–2 on both fresh contracts. Each has a finalized GenLayer `COMPLIANT` check against the deployed signer-registry source and a matching replay-protected Base decision receipt.

1. **Compliant repayment (loan 0):** created and activated on GenLayer, adjudicated compliant, relayed to Base, drawn, repaid with 5% interest, and settled.
2. **Compliant draw-ready (loan 1):** created and activated on both chains, adjudicated compliant on GenLayer, and unlocked on Base while principal and collateral remain escrowed.
3. **Independent repeat (loan 2):** a distinct borrower and check prove the same full create → activate → adjudicate → relay path is repeatable and replay-safe.

GenLayer check transactions: `0x6ee763cb8e1614da34081686a7bf462d5a906209affd9417f858e3534aecc03a`, `0x742e009be17797ff6376f4b9d095901e45ad8893a3c2ef5f620f7878d3948dd1`, and `0x465cbdc4686bbf2de1ba38fb811472ee6e404bc83f417ac03122b11edf28504e`. Base relay transactions: `0x51e496c607b9c6c12c81e3436bce8e9231b6714d43be59790db56944fac68a48`, `0x4b2427c6e54be35f8d5ce02b6f2a3e0cd0f1fc3e19e8f77b27e54a7bc282b05f`, and `0x1ade36c02c6653a779da91bdc554c6834b433aaa28ace2b2f8e84c4b5d858823`.

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
