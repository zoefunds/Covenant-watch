# Covenant Watch — Frontend

Next.js 16 (App Router) + TypeScript + Tailwind v4 app for Covenant Watch.
Every loan/covenant write goes directly to the GenLayer contract via
`genlayer-js` from the connected wallet — the backend is only ever a
read-cache and SIWE auth service, never a proxy for a transaction. See
repo-root [`README.md`](../README.md) for the overall project and
[`memory.md`](../memory.md) for build history.

Live: https://covenant-watch.vercel.app

## Design system

"Obsidian Assurance" — a dark theme implemented as real Tailwind tokens in
`src/app/globals.css`'s `@theme inline` block: Inter for UI chrome,
JetBrains Mono with `tabular-nums` for all onchain numeric/hash data, 4px/8px
radii, a `1px solid #00F0FF` focus ring.

## Wallet connection: Reown (WalletConnect) AppKit

Wallet connection uses `@reown/appkit` + `@reown/appkit-adapter-wagmi`
(backed by `wagmi`/`viem`), configured in `src/lib/appkit.ts` against a
`CaipNetwork` built directly from `genlayer-js`'s own `chains.studionet`
definition — never a separately-invented chain config.

**Connecting a wallet is not authentication.** `src/context/WalletContext.tsx`
keeps the AppKit-connected `address` and the backend-authenticated
`sessionAddress` as separate state. Signing in is a real SIWE round trip:
`POST /auth/nonce` → `personal_sign` via the AppKit-connected wallet's own
EIP-1193 provider → `POST /auth/verify` → httpOnly session cookie. If the
connected wallet's address stops matching the authenticated session address
(account switch, disconnect), the session is treated as unauthenticated
immediately — never a stale "signed in" state for the wrong address.

`src/components/AppShell.tsx` renders a loading placeholder until a
`useEffect`-driven mounted flag flips, because AppKit's hooks require
`createAppKit()` to have already run client-side and would otherwise throw
during Next's static prerender pass.

## Contract wiring

`src/lib/contract.ts` mirrors `contracts/covenant_watch.py`'s public methods
exactly: `create_loan`, `lock_collateral`, `claim_principal`,
`trigger_covenant_check`, `submit_challenge_evidence`,
`finalize_covenant_check`, `repay_loan`, `settle_matured_loan`, the safe
backward-compatible `reclaim_collateral_timeout`, `cancel_loan`,
`claim_settlement`, plus every `@gl.public.view`. Two details
worth knowing if you touch this file:

- `create_loan`'s `covenants_json` array items take a plain `threshold`
  float — the contract scales it internally (`_scale()`), the frontend
  never pre-scales it.
- Every loan/covenant/check view already returns `status` as the
  human-readable string the contract itself emits (e.g. `"BREACH_TIER1"`,
  `"INCONCLUSIVE"`) — never a raw int to decode client-side.

`src/lib/genlayer.ts` wraps the real `genlayer-js` client
(`createClient`, `readContract`, `writeContract`,
`waitForTransactionReceipt`). `src/lib/tx.ts` drives every write through
`submitted → pending → finalized/failed` off the SDK's own transaction
status enum, explicitly requesting `FINALIZED` instead of the SDK's
`ACCEPTED` default and requiring `FINISHED_WITH_RETURN` so a finalized revert
remains a failure — never a `setTimeout` standing in for real status.

## Pages

- `/` — landing page.
- `/loans` — dashboard: backend-indexed loan list, a per-loan Collateral
  Health Gauge, KPI row (total escrowed, loan count, in-grace count,
  breached count), and status filter tabs.
- `/loans/new` — full covenant-builder form: per-covenant source
  type/three-publisher URL set/condition/operator/threshold, SSRF-protected
  informational previews via `/covenants/preview-source`, distinct-hostname
  enforcement, client-side
  vague-condition-phrase rejection mirroring the contract's own
  `VAGUE_CONDITION_FRAGMENTS` list, a bounded challenge-window slider, and a
  pre-deployment summary card.
- `/loans/[id]` — loan detail and every lifecycle action (lock collateral,
  claim principal, repay, cancel, permissionless maturity settlement, claim
  settlement), each gated by contract state, with contract-clock-synchronized
  countdowns and finalized one-shot actions disabled. Drawn/unpaid loans
  default after maturity grace; undrawn loans unwind both escrows.
- `/loans/[id]/covenants/[covenantId]/check` — trigger a covenant check
  (respecting the real on-chain cooldown via `get_cooldown_remaining`),
  with a Pinned Snapshot Hash display, a Validator Consensus Split Meter
  fed from the transaction receipt's consensus data, and distinct
  INCONCLUSIVE-state treatment. Cooldown and challenge-window actions are
  disabled by live countdowns that mirror contract-enforced timestamps.
- `/loans/[id]/covenants/[covenantId]/challenge` — additive-only evidence
  submission during an open challenge window; the form has no field that
  can edit or replace the original pinned source set or prior evidence. The
  contract accumulates three distinct evidence hosts before reevaluation.
- `/history` — cross-loan check/challenge history from the backend cache.
- `/profile` — session address and the connected user's loans by role.
- `/settings` — network/contract/backend health, sign-out, and an explicit
  list of what's deferred (out of v1 scope) rather than faked.

## Environment variables

See `.env.example`:

```
NEXT_PUBLIC_CONTRACT_ADDRESS      # deployed contract address
NEXT_PUBLIC_GENLAYER_NETWORK      # localnet | studionet | testnetAsimov | testnetBradbury | mainnet
NEXT_PUBLIC_BACKEND_URL           # FastAPI backend base URL (read cache + auth only)
NEXT_PUBLIC_GENLAYER_EXPLORER_URL # https://explorer-studio.genlayer.com/
NEXT_PUBLIC_REOWN_PROJECT_ID      # Reown (WalletConnect) AppKit project id — https://dashboard.reown.com
```

All `NEXT_PUBLIC_*` variables are safe to ship to the browser bundle by
design — a public contract address, network name, API base URL, explorer
URL, and WalletConnect project id, nothing secret.

## Local development

```bash
npm install
cp .env.example .env.local
# defaults already point at the live deployed contract
# (0x5c3Fe893aaaa9C0416F76812c3903Cf4AfA528A7, studionet) and a working
# Reown project id — only NEXT_PUBLIC_BACKEND_URL needs to match wherever
# you're running backend/ (default http://localhost:8000)

npm run dev      # requires Node >=20.9
npm run build    # production build
npm run lint
```

## Tests / verification

There is no dedicated component test suite. The current verification baseline
is ESLint, `tsc --noEmit`, and a complete Next.js production build. The
separate StudioNet harness exercised real `genlayer-js` writes, finalized
receipts, validator consensus, immediate state rereads, repayment, and
settlement against the production contract. Browser-wallet approval remains a
manual UI check because automation uses unlocked test accounts rather than a
wallet extension.

## Deployment

Deployed to Vercel (project `covenant-watch`). See the repo-root
[`DEPLOYMENT.md`](../DEPLOYMENT.md) §4 for the full Vercel deploy steps and
required production environment variables.
