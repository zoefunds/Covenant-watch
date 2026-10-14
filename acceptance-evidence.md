# Live remediation acceptance evidence

Run completed 14 October 2026 against a fresh zero-loan deployment pair. The complete machine-readable record is checked in as [`acceptance-evidence.json`](./acceptance-evidence.json); it contains every Base receipt, USDC before/after balance, GenLayer transaction hash, validator vote, and final contract tuple.

## Deployment and identities

- Base escrow: [`0xbF8F70Db480d003Dd6c5629c50b1f9Bf3Adc9E9b`](https://sepolia.basescan.org/address/0xbF8F70Db480d003Dd6c5629c50b1f9Bf3Adc9E9b)
- Base deployment: [`0x1690edbcf6b5a519ac5c574235579e88a966185f3596251dffc33691b6e9df68`](https://sepolia.basescan.org/tx/0x1690edbcf6b5a519ac5c574235579e88a966185f3596251dffc33691b6e9df68)
- GenLayer adjudicator: [`0x1b4BA5Fe8894648E4B90d80f2DA5d53880CcfD7b`](https://explorer-studio.genlayer.com/address/0x1b4BA5Fe8894648E4B90d80f2DA5d53880CcfD7b)
- GenLayer deployment: [`0x9698a8fa9f6db79cbcda2a0986243d4b60f0f993003049864bdccf7f0aa0634a`](https://explorer-studio.genlayer.com/transactions/0x9698a8fa9f6db79cbcda2a0986243d4b60f0f993003049864bdccf7f0aa0634a)
- Circle Base Sepolia USDC: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
- Lender/decision signer: `0x7401c129EDfc26E68FE19309fE461eb3Db1058Eb`
- Borrower/relayer: `0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A`

The GenLayer deployment finalized with five agreeing validators. The Base constructor permanently binds this GenLayer address and chain ID into its signed-decision domain.

## Scenario 1 — compliant draw, repayment, and withdrawals

Loan `0` moved 1 USDC principal and 1.5 USDC collateral into escrow. GenLayer finalized a compliant decision. A deliberately forged relay was mined with status `0` ([receipt](https://sepolia.basescan.org/tx/0x0920ac6698742a032a54b0c3ef30b6b1d68691375dbe336d7cfa64c4ef51aeb4)); the authentic signed decision succeeded ([receipt](https://sepolia.basescan.org/tx/0x5b4bb7a40a98f6ece0485569a578eda1064eac6834606b9441268986dce354b8)). The borrower then drew principal, repaid exactly 1.05 USDC, and both parties withdrew their rightful settlements. Final status: `REPAID`; escrow balance: zero.

## Scenario 2 — challenge reconciliation and three-tier breach

Loan `1` froze three distinct covenant identities and their consequence bounds. Three additional publisher URLs were submitted during the challenge process, but adjudication preserved and reconciled the original source set. Three separately finalized and authenticated breach decisions produced tier 1, tier 2, then terminal tier 3 default:

- [breach relay 1](https://sepolia.basescan.org/tx/0xee8ddc93b9e68bc3209a81869063e11fa1732fce6621c25a162a91ad2fc8e4af)
- [breach relay 2](https://sepolia.basescan.org/tx/0xa330e98f1b388f72f22345de300c27b96ac151219e4d2ac7931043f4a3c39a84)
- [breach relay 3](https://sepolia.basescan.org/tx/0x2d53b2c45bde943089c8d07cd7ce6f7a1eb6ee08cceb30eafcaf4f0cd9c89dd2)

Final status: `DEFAULTED`; breach tier: `3`; bounded interest: `650` bps. The lender withdrew the terminal settlement and escrow returned to zero.

## Scenario 3 — undrawn maturity settlement

Loan `2` escrowed principal and collateral but was never drawn. After maturity plus the 60-second grace period, permissionless settlement succeeded ([receipt](https://sepolia.basescan.org/tx/0xd81a6db9de4dd975a582da1179f45bc6f47f83b714cd25c4b22e1145e8f613e7)). The lender recovered 1 USDC principal and the borrower recovered 1.5 USDC collateral. Final status: `TIMEOUT_RECLAIMED`; escrow balance: zero.

## Regression gates

- Foundry covers repeated same-covenant checks, drawdown/maturity boundaries, forged and excessive relays, mismatched commitments, replay, relay recovery, repayment, and settlement.
- Backend/direct tests cover index, relay, API, and serialization behavior.
- Frontend lint, TypeScript, and production build validate the browser-wallet flow and live indexed-loan rendering.

The runner is [`tests/e2e/security_acceptance.py`](./tests/e2e/security_acceptance.py). It reads private keys only from environment variables and never writes them into the evidence artifact.
