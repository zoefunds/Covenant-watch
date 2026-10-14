# V3 cross-chain acceptance evidence

Verified 14 October 2026 against the current production pair:

- Base escrow: [`0xcCebA6072A607fed1674547B68EF3Fb1b30F867e`](https://sepolia.basescan.org/address/0xcCebA6072A607fed1674547B68EF3Fb1b30F867e)
- Base deployment: [`0xf17e5d27d9451e50a16130e314840a71e2cbc79acb875b086f62f5d9bea45a29`](https://sepolia.basescan.org/tx/0xf17e5d27d9451e50a16130e314840a71e2cbc79acb875b086f62f5d9bea45a29)
- GenLayer adjudicator: [`0x646Ca53B8CafC1e1242c67AC9059F1c53f7B2E4D`](https://explorer-studio.genlayer.com/address/0x646Ca53B8CafC1e1242c67AC9059F1c53f7B2E4D)
- GenLayer deployment: [`0x2828a9f9836a985f46d2e655454d0ee373681f27bc2824a748552e4af339814e`](https://explorer-studio.genlayer.com/transactions/0x2828a9f9836a985f46d2e655454d0ee373681f27bc2824a748552e4af339814e)
- Circle Base Sepolia USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`

The checked-in [`acceptance-evidence.json`](./acceptance-evidence.json) contains Base receipts, USDC before/after balances, GenLayer hashes and validator votes, state readbacks, and the recovered incomplete-transaction path. No private key is recorded.

## V3 commitment integrity

`COVENANT_WATCH_LOAN_V3` includes the ordered covenant hashes plus a separately recomputable `COVENANT_WATCH_PENALTY_SCHEDULE_V1` hash. GenLayer derives the schedule from its validated covenant definitions. Base derives it independently from the supplied `tier1StepBps` and `tier2SeizureBps` arrays before accepting USDC. A one-basis-point mismatch is rejected even when both values remain below global limits.

## Wallet-signed compliant lifecycle

Loan 0 was created from a fresh zero-loan pair using separate lender and borrower wallets:

- 1 USDC principal escrow: [receipt](https://sepolia.basescan.org/tx/0xb00dc0947a766a9425d3023b13ca755e5530940deafc018bc4bf51d4cda2012b)
- 1.5 USDC collateral stake: [receipt](https://sepolia.basescan.org/tx/0x0603165e03886f126886c14363d202dcd65beb3c43ca010b5cf5af044f57836b)
- forged verdict rejected with Base status 0: [receipt](https://sepolia.basescan.org/tx/0xdfb6871ebb3ee05a02055d527747a884af36182934c89ea558301af87e1a6f1d)
- authenticated compliant relay: [receipt](https://sepolia.basescan.org/tx/0x255d17363feb53ec18e629aa17fc90a41b1a6534c6bf968243d722e749835a00)
- borrower principal draw: [receipt](https://sepolia.basescan.org/tx/0x24296e3cb7bb9d41223255f6cac6da9931b98d3978f88ccfc77324ee867553ab)
- exact 1.05 USDC repayment: [receipt](https://sepolia.basescan.org/tx/0xba9e132a5fd16e7800099e1e4f72c151ed5eec57f75e46a7988480e4e6857339)
- lender and borrower withdrawals: [lender](https://sepolia.basescan.org/tx/0xf5b55243d21cf60aee16c941a4ed091cc3aadb9218d46ae451ad61feedb5a3cf), [borrower](https://sepolia.basescan.org/tx/0x06b503280b6dbaa118e2a58652bbce37a4e60b107499e806f3af62f5cba84890)

Final Base status is `REPAID`; principal, collateral, and both claimable balances are zero.

## Incomplete-transaction recovery and default

Loan 1 encountered a real GenLayer `CANCELED / NO_MAJORITY` transaction (`0xa5119c…9133`). No Base decision was applied. The runner now distinguishes terminal cancellation from pending state, retries only terminal canceled writes, and requires the GenVM leader result to be `SUCCESS`; validator agreement on a rollback is explicitly rejected.

The missing checks were recovered without another Base loan, approval, or collateral transfer. Check 3 stored three preauthorized challenge URLs, preserved the original source hash, and finalized `BREACH` with the note “challenge did not reconcile the original committed breach.” Three signed V3 relays then produced tier 1, tier 2, and terminal default:

- [relay 1](https://sepolia.basescan.org/tx/0x7c396aa9cee5ba0603e70167ffa71ea92853e0aac6e2d25603ef21c2682e13d8)
- [relay 2](https://sepolia.basescan.org/tx/0x63986934b7258c884e9b7dba35274bb677a243eaef93a5e739b09f2a87945f5d)
- [relay 3](https://sepolia.basescan.org/tx/0x532cbb1e6e095ea4e6f2707d7be09d4dcd472b4f225210cfa5fe71cb0a93b11a)
- [terminal lender withdrawal](https://sepolia.basescan.org/tx/0xd61ae51b3fecdd06fbd06ff2428ce8070cd3688468e0adbbb885fe524ad63010)

Final Base status is `DEFAULTED`, breach tier is 3, interest is 650 bps, and escrow/claimable balances are zero.

## Regression gates

- Foundry: 13 passed. This includes within-limit penalty mismatch rejection, signer rotation, replay, pairing mismatch, failed relay recovery, post-deadline draw rejection, and incomplete-origination cancellation/refund.
- Backend/direct: 30 passed. GenLayer registration rejects modified penalties, modified financial terms, and duplicate Base IDs.
- Frontend: ESLint, TypeScript, and production build passed.
- Production API: healthy with `last_error: null`, indexing current loans 0 and 1 as `REPAID` and `DEFAULTED`.
- Public Settings displays both current contract addresses; public loan pages render current indexed state.
