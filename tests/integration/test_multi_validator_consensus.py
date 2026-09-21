"""Genuine multi-validator consensus on an OFFCHAIN covenant check.

Unlike tests/direct/ (leader function only, no validator/consensus round
at all -- see its module docstring), a `gltest` run against a live network
with more than one validator actually runs `_run_covenant_evaluation`'s
`gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` through REAL,
independent leader + validator executions: each validator independently
re-fetches the pinned URL and re-runs the LLM prompt, and GenVM's
consensus mechanism requires them to agree (via `_covenant_results_agree`)
before the transaction finalizes.

This test asserts on the transaction receipt's own `consensus_data.votes`
-- which reflects genuine per-validator agreement, not a leader-only
shortcut -- and needs a network configured with >1 validator (e.g.
`glsim --validators 5 ...`, or Studio/testnet's own validator set).
"""

from gltest.assertions import tx_execution_succeeded

from conftest import covenants_json, deploy_covenant_watch, future_ts, offchain_covenant


def test_multi_validator_agreement_on_compliant_check(lender, borrower,
                                                        offchain_pages_base_url,
                                                        require_payable, require_llm):
    contract = deploy_covenant_watch(lender)
    url = f"{offchain_pages_base_url}/compliant"
    cov = offchain_covenant(url=url, field="reserve_ratio", op=">=", threshold=1.0)

    tx = contract.create_loan(
        args=[borrower.address, 2_000_000, 500, future_ts(), covenants_json(cov), 0],
    ).transact(value=1_000_000)
    assert tx_execution_succeeded(tx)
    loan_id = 0
    tx = contract.connect(borrower).lock_collateral(args=[loan_id]).transact(value=2_000_000)
    assert tx_execution_succeeded(tx)

    tx = contract.trigger_covenant_check(args=[loan_id, 0]).transact()
    assert tx_execution_succeeded(tx)

    votes = tx.get("consensus_data", {}).get("votes", {})
    assert len(votes) >= 2, (
        f"expected a multi-validator network (>=2 votes) to genuinely "
        f"exercise leader/validator consensus; got {len(votes)} vote(s): "
        f"{votes!r}. Re-run glsim with --validators 5 (or more), or target "
        f"a network whose validator set is already >1 (studionet, "
        f"testnet_bradbury)."
    )
    assert all(v == "agree" for v in votes.values()), (
        f"expected every validator to independently reach the same "
        f"structured result (per _covenant_results_agree's tolerance rule) "
        f"and vote 'agree'; got {votes!r}"
    )

    check = contract.get_check(args=[0]).call()
    assert check["status"] == "COMPLIANT"
