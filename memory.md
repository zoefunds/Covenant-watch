# Covenant Watch current operational record

Last verified: 13 October 2026 (Africa/Lagos).

This file records current state only. Retired addresses, old transaction demonstrations, superseded wallet stacks, and resolved failures are intentionally omitted; use Git history for historical investigation.

## Production inventory

| Component | Current value |
|---|---|
| GenLayer network | StudioNet |
| GenLayer adjudicator | `0xb86d1525014c80F98E7f0C3Be2af60AF3ab761F8` |
| GenLayer deployment transaction | `0x15aeb14989c76229ad0e409cb5affdbafea1aca643eef0113eafd5aecf3a4d9b` |
| Base network | Base Sepolia, chain ID `84532` |
| Base escrow | `0x6b806484E938E8Bf5eD65D1841543931240834ef` |
| Base deployment transaction | `0x7240cc53bb05537aee0ced6675a4760d14204bbdd205676e2b1b8c34c44b5d1f` |
| Circle test USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Base relayer | `0x35F5ea45122eE7Dd5Ec6aA6aab961E9147e3e9e8` |
| Frontend | https://covenant-watch.vercel.app |
| Vercel project / deployment | `covenant-watch` / `dpl_BG3fddp9AQWHYgTYFpESUZ8fJJ8J` |
| Backend | https://covenant-watch-api.fly.dev |
| Fly app / region | `covenant-watch-api` / `iad` |

The GenLayer deployment is finalized and successful with five agreeing validators. Both chain counters are zero, and the backend `/loans` response is empty. No live E2E loan has been submitted to the fresh pair.

## Live architecture

- Base is the only value layer and holds all principal and collateral USDC.
- GenLayer stores paired loan/covenant metadata and adjudicates evidence.
- The frontend directly uses a user-selected EIP-6963 provider for SIWE and all wallet writes. Reown and wagmi are absent.
- The backend indexes GenLayer, enriches loans with Base state, authenticates sessions, previews URLs, and relays finalized decisions with a dedicated Base key.
- The relayer key is stored only as `BASE_RELAYER_PRIVATE_KEY` in Fly secrets. Never place it in documentation, source, frontend variables, or logs.

## Current transaction sequence

1. Lender approves Base USDC and creates the Base escrow loan.
2. The same wallet switches to GenLayer and registers the corresponding adjudication loan.
3. Borrower approves and stakes Base USDC, then records the confirmed Base transaction on GenLayer.
4. GenLayer checks and challenges reach finality.
5. Backend relays the finalized result to Base and records the confirmed Base hash on GenLayer.
6. User wallets draw, repay, settle, or claim on Base.

Loan IDs must match across both fresh deployments. The frontend counter guard blocks origination when they diverge.

## Deployment invariants

- Fly `CONTRACT_ADDRESS` and Vercel `NEXT_PUBLIC_CONTRACT_ADDRESS` equal the current GenLayer address.
- Fly `BASE_ESCROW_ADDRESS` and Vercel `NEXT_PUBLIC_BASE_ESCROW_ADDRESS` equal the current Base address.
- Both services use the Circle Base Sepolia USDC address above.
- Address changes require a Fly restart and Vercel rebuild.
- Never treat GenLayer `ACCEPTED` as final; require successful `FINALIZED` execution.
- Never represent historical E2E receipts as evidence for a new contract pair.
- Resolve partial cross-chain failures from confirmed state and transaction hashes; do not blindly repeat origination.

## Acceptance status

Deployment receipts and zero-state reads have been verified. The local Foundry suite passed 3/3, the backend suite passed 17/17, and frontend lint, type checking, and production build passed after the current wallet and contract integration. These are local checks, not live-chain proof. Live USDC escrow, collateral movement, adjudication, and relay on the fresh addresses remain for user-run acceptance testing.
