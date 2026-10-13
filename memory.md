# Covenant Watch current operational record

Last verified: 13 October 2026 (Africa/Lagos).

This file records current state only. Retired addresses, old transaction demonstrations, superseded wallet stacks, and resolved failures are intentionally omitted; use Git history for historical investigation.

## Production inventory

| Component | Current value |
|---|---|
| GenLayer network | StudioNet |
| GenLayer adjudicator | `0x1EC71Df45C68F9F52A155DbBC8def172B00819C4` |
| GenLayer deployment transaction | `0x375f98f42157f8e3cf941074036f2d26cc140c3fae02b3a1233d630fbca60ffa` |
| Base network | Base Sepolia, chain ID `84532` |
| Base escrow | `0x37913648E096a6E8e97A2f5F31473e31c90c2Fb2` |
| Base deployment transaction | `0x3ffd97e520394dc4577420b3df987711bb857f8a305e7868fc6674075dfd8dfb` |
| Circle test USDC | `0x036CbD53842c5426634e7929541eC2318f3dCF7e` |
| Base relayer | `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb` |
| Frontend | https://covenant-watch.vercel.app |
| Vercel project / deployment | `covenant-watch` / `dpl_BG3fddp9AQWHYgTYFpESUZ8fJJ8J` |
| Backend | https://covenant-watch-api.fly.dev |
| Fly app / region | `covenant-watch-api` / `iad` |

The GenLayer deployment is finalized and successful with five agreeing validators. Both chain counters are three after the live acceptance run, and the backend `/loans` response contains three paired loans.

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
