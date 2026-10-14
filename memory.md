# Covenant Watch current operational record

Last verified: 13 October 2026 (Africa/Lagos).

This file records current state only. Retired addresses, old transaction demonstrations, superseded wallet stacks, and resolved failures are intentionally omitted; use Git history for historical investigation.

## Production inventory

| Component | Current value |
|---|---|
| GenLayer network | StudioNet |
| GenLayer adjudicator | `0x646Ca53B8CafC1e1242c67AC9059F1c53f7B2E4D` |
| GenLayer deployment transaction | `0x2828a9f9836a985f46d2e655454d0ee373681f27bc2824a748552e4af339814e` |
| Base network | Base Sepolia, chain ID `84532` |
| Base escrow | `0xcCebA6072A607fed1674547B68EF3Fb1b30F867e` |
| Base deployment transaction | `0xf17e5d27d9451e50a16130e314840a71e2cbc79acb875b086f62f5d9bea45a29` |
| Circle test USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Base relayer | `0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A` |
| Decision signer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Frontend | https://covenant-watch.vercel.app |
| Vercel project / deployment | `covenant-watch` / `dpl_JAxumXRuTiSeeMDKR36sedevdeFi` |
| Backend | https://covenant-watch-api.fly.dev |
| Fly app / region | `covenant-watch-api` / `iad` |

The GenLayer deployment is finalized and successful with five agreeing validators. Both chain counters are two after the V3 acceptance run, and the backend `/loans` response contains both paired loans.

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

Deployment receipts, live transaction receipts, finalized GenVM results, validator votes, contract-state readbacks, and Base USDC balance deltas have been verified in the acceptance artifact. The local Foundry suite passed 9/9, the backend/direct suite passed 28/28, and frontend lint, type checking, and production build passed.
