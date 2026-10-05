# Covenant Watch audit

Date: 2026-10-05

## Enforced trust boundary

- The backend has no contract write path, funded key, verdict endpoint, or
  settlement authority. It only indexes public contract views and offers an
  informational URL preview that never enters consensus.
- The frontend sends writes directly from the connected wallet to the
  contract. Every authorization, state transition, deadline, cooldown,
  consequence, and transfer is re-checked by the contract.
- An off-chain check accepts only an immutable creation-time set of 3–5 HTTPS
  URLs on distinct publisher hostnames. The nondeterministic leader and every
  validator independently render every URL and run each extraction prompt.
  No backend-fetched body or verdict is accepted.
- Equivalence requires the same status, the same rendered-input hash, and a
  bounded numeric-value difference. The contract—not the model—derives
  COMPLIANT or BREACH from the extracted number and immutable operator and
  threshold.
- A strict publisher majority must corroborate a numeric value within 2%; the
  full fetched bundle is hashed and bounded per-publisher extraction
  diagnostics are stored. A challenge needs its own three distinct publisher
  hosts, is bound to the frozen primary hash, and is independently fetched by
  every validator. A submitter's note alone cannot change a verdict.
- On-chain covenants call the precommitted source contract directly during
  contract execution. Malformed/unavailable reads become INCONCLUSIVE.
  Off-chain challenge evidence cannot override deterministic on-chain data.

## Correctness and security fixes

- Frontend receipt polling explicitly waits for `FINALIZED`, never the SDK's
  default `ACCEPTED`, requires `FINISHED_WITH_RETURN` (a finalized revert is
  a failure), and immediately re-reads contract state after finality.
- Maturity, settlement, cooldown, and challenge-window countdowns update every
  second from a contract-clock offset and disable actions until the contract
  deadline is eligible.
- Successful one-shot actions are disabled immediately to prevent duplicate
  submissions while refreshed chain state propagates.
- Covenant checks require an active collateralized loan; expired offers cannot
  lock collateral. Principal remains escrowed until every covenant's latest
  check is finalized `COMPLIANT`; the contract enforces this independently of
  the frontend. Repayment requires that principal was drawn.
- Breach tiers advance across the whole loan, including breaches of different
  covenants. Default and timeout return any undrawn principal to the lender.
- Terminal loans ignore stale pending consequences, exact repayment prevents
  partial-value stranding/overpayment, and all outgoing transfers use the
  contract's zero-before-transfer choke point.
- Maturity settlement is permissionless and deterministic after a 14-day
  repayment grace: undrawn loans unwind each party's escrow, while drawn and
  unpaid loans default and credit all remaining collateral to the lender.
- Indexer passes are single-flight through both a process lock and a PostgreSQL
  transaction advisory lock across replicas. A timed-out synchronous RPC
  worker retains its locks until it actually exits, preventing thread
  accumulation and rejecting overlapping request-triggered refreshes with
  HTTP 409.
- Covenant/evidence URLs require HTTPS and reject obvious local/private
  literal targets. Field names, addresses, numeric ranges, JSON size, evidence
  counts, and consequence ranges are contract-bounded.

## Verification

- Contract direct suite: 38 passed.
- Backend suite: 17 passed.
- Frontend ESLint: passed.
- Frontend TypeScript (`tsc --noEmit`): passed.
- `git diff --check`: passed.
- The Next.js webpack production build completed. It reported pre-existing
  optional connector-resolution warnings from the Reown/Wagmi dependency tree
  (`@metamask/connect-evm`, `@walletconnect/ethereum-provider`, and Tempo's
  `accounts` import), but emitted every application route successfully.
- The five-validator GLSim launcher was repaired for the current SDK's
  version-isolated contract registries. Repeated deployments now finalize
  without cross-contract class contamination.
- StudioNet deployment `0xcabD9990BdC2B45f22C60b4Ea519041e42c3E980`
  finalized with validator consensus. A live escrow lifecycle on loan 0
  finalized a `COMPLIANT` check at `21000000.000000`, corroborated 3/3
  independent publishers with three agreeing execution validators, then
  repaid and claimed both settlement balances successfully.

## Residual properties

- No single publisher is authoritative. A dishonest or unavailable minority
  fails to control the result, as covered by the malicious-outlier test.
  Publisher collusion remains an external-oracle assumption: software cannot
  cryptographically prove a real-world statement without signed attestations
  or a stronger oracle network.
- LLM extraction is probabilistic. Economic classification is deterministic
  and validators must agree on source bytes/status/value, so ambiguity fails
  closed through disagreement or INCONCLUSIVE rather than applying a penalty.
- The backend cache is eventually consistent and non-authoritative. Fund and
  compliance writes remain safe if it is stale or unavailable because the
  contract enforces every rule.
- The installed local GLSim still does not forward transaction value into
  `gl.message.value`, so payable local escrow cases skip by design. This is no
  longer a production gate: the complete payable path and genuine LLM-backed
  multi-validator source check passed on StudioNet as recorded above.
