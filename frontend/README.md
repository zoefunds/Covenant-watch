# Covenant Watch frontend

Next.js 16, TypeScript, and Tailwind v4 browser application. Production: https://covenant-watch.vercel.app.

## Wallet connection

The app follows Meme Olympics' direct EIP-6963 pattern. It discovers installed wallets, lets the user choose among providers, and retains that exact EIP-1193 provider for SIWE, Base Sepolia, and GenLayer StudioNet. Reown and wagmi are not used. Every write switches the selected wallet and verifies the resulting network before submission.

Connection and authentication remain separate. `WalletContext` tracks the connected address and authenticated session address independently. SIWE performs `/auth/nonce` → `personal_sign` → `/auth/verify`; an account switch or disconnect invalidates a mismatched UI session immediately.

## Cross-chain transaction flow

- Origination: Base USDC `approve` → Base `createLoan` → GenLayer `create_loan`.
- Borrower activation: Base USDC `approve` → Base `stakeCollateral` → GenLayer `activate_base_loan`.
- Adjudication: GenLayer `trigger_covenant_check`, additive challenge evidence, and `finalize_covenant_check`.
- Economics: Base `claimPrincipal`, `repay`, `cancel`, `settleMatured`, and `claimSettlement`.
- Relay: the backend, not the browser, sends finalized decisions to Base and records the confirmed hash on GenLayer.

Origination first compares Base and GenLayer loan counters. A mismatch stops the flow to avoid assigning one ID to unrelated records. Because the two-chain sequence is not atomic, confirmed hashes remain visible if a later step fails; recovery must use those confirmed records instead of blindly creating another loan.

`src/lib/base.ts` contains Base chain switching, reads, ERC-20 approvals, and escrow writes. `src/lib/contract.ts` and `src/lib/genlayer.ts` contain GenLayer calls and finality handling. GenLayer writes require `FINALIZED` plus successful execution, not merely `ACCEPTED`.

## Current contracts

```text
NEXT_PUBLIC_CONTRACT_ADDRESS=0x646Ca53B8CafC1e1242c67AC9059F1c53f7B2E4D
NEXT_PUBLIC_GENLAYER_NETWORK=studionet
NEXT_PUBLIC_BASE_USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
NEXT_PUBLIC_BASE_ESCROW_ADDRESS=0xcCebA6072A607fed1674547B68EF3Fb1b30F867e
NEXT_PUBLIC_BACKEND_URL=https://covenant-watch-api.fly.dev
```

All `NEXT_PUBLIC_*` values are public configuration. No private key belongs in the frontend environment.

## Routes

- `/loans` renders only backend-indexed loans and live Base enrichment; there are no checked-in verified-loan cards.
- `/loans/new` creates the paired Base/GenLayer loan and shows each transaction stage.
- `/loans/[id]` exposes role- and state-appropriate Base lifecycle actions.
- Covenant check and challenge routes submit only GenLayer adjudication calls.
- `/history`, `/profile`, and `/settings` use the indexed API and current public configuration.

The V3 acceptance run created two paired loans on these contracts. `/loans` is populated from indexed chain state rather than fixtures.

## Local development and verification

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
npm run lint
npx tsc --noEmit
npm run build -- --webpack
```

There is no dedicated component-test suite. Lint, type checking, and a production build are the current local verification baseline. Browser-wallet approvals, cross-network switching, USDC movement, GenLayer finality, and relay remain live acceptance checks; the old E2E receipts do not prove the fresh deployments.

Deploy from this directory with `vercel --prod --yes`. The current production deployment ID is `dpl_JAxumXRuTiSeeMDKR36sedevdeFi`.
