"""Real ONCHAIN covenant check: a genuine cross-contract read via
`gl.get_contract_at(...)` inside `CovenantWatch._evaluate_onchain`, against
a second, independently deployed helper contract
(`contracts/test_helpers/mock_signer_registry.py`).

This is the exact scenario tests/direct/ could NOT exercise -- the
direct-mode harness has no `CallContract` dispatch implementation (see
memory.md and the `pytest.skip` left in
tests/direct/test_covenant_watch.py::test_inconclusive_from_unreachable_onchain_source).
Here it runs for real: two contracts are deployed independently, the
covenant's source_ref is set to the helper's real deployed address, and
`trigger_covenant_check` performs a real `CallContract` to read
`get_signer_count()` off it.

Deploying two distinct contract *files* in the same GLSim session hits a
separate, unrelated GLSim bug (a process-wide "only one contract class"
loader global reused from gltest's direct-mode SDK -- see
tests/integration/run_glsim_patched.py for the full writeup and the fixed
launcher). Start glsim via that launcher, not the bare `glsim` command, to
run this file locally.
"""

from gltest.assertions import tx_execution_succeeded

from conftest import (
    covenants_json,
    deploy_covenant_watch,
    deploy_mock_signer_registry,
    future_ts,
    onchain_covenant,
)


def test_onchain_cross_contract_compliant(lender, borrower, require_payable):
    registry = deploy_mock_signer_registry(lender, initial_signer_count=5)
    assert registry.get_signer_count(args=[]).call() == 5

    contract = deploy_covenant_watch(lender)
    cov = onchain_covenant(source_ref=registry.address, field="signer_count", op=">=", threshold=3)

    tx = contract.create_loan(
        args=[borrower.address, 2_000_000, 500, future_ts(), covenants_json(cov), 0],
    ).transact(value=1_000_000)
    assert tx_execution_succeeded(tx)
    loan_id = 0

    tx = contract.connect(borrower).lock_collateral(args=[loan_id]).transact(value=2_000_000)
    assert tx_execution_succeeded(tx)

    tx = contract.trigger_covenant_check(args=[loan_id, 0]).transact()
    assert tx_execution_succeeded(tx)

    check = contract.get_check(args=[0]).call()
    assert check["status"] == "COMPLIANT", (
        f"real cross-contract read of signer_count=5 against threshold "
        f">=3 should be COMPLIANT; got {check!r}"
    )
    assert "signer_count=5" in check["observed_note"]


def test_onchain_cross_contract_breach_triggers_consequence(lender, borrower, require_payable):
    """Drop the real registry's signer_count below the covenant threshold
    (via a real write transaction on the helper contract), then trigger a
    real check and confirm CovenantWatch's deterministic consequence
    pipeline (_apply_consequence) actually fires off the genuinely-fetched
    BREACH result -- interest step-up, loan status BREACH_TIER1."""
    registry = deploy_mock_signer_registry(lender, initial_signer_count=5)

    contract = deploy_covenant_watch(lender)
    cov = onchain_covenant(source_ref=registry.address, field="signer_count", op=">=", threshold=3,
                            tier1=500)

    tx = contract.create_loan(
        args=[borrower.address, 2_000_000, 500, future_ts(), covenants_json(cov), 0],
    ).transact(value=1_000_000)
    assert tx_execution_succeeded(tx)
    loan_id = 0
    tx = contract.connect(borrower).lock_collateral(args=[loan_id]).transact(value=2_000_000)
    assert tx_execution_succeeded(tx)

    # Real state-changing write on the helper contract -- drops below the
    # covenant's pinned threshold.
    tx = registry.set_signer_count(args=[1]).transact()
    assert tx_execution_succeeded(tx)
    assert registry.get_signer_count(args=[]).call() == 1

    tx = contract.trigger_covenant_check(args=[loan_id, 0]).transact()
    assert tx_execution_succeeded(tx)

    check = contract.get_check(args=[0]).call()
    assert check["status"] == "BREACH", (
        f"real cross-contract read of signer_count=1 against threshold "
        f">=3 should be BREACH; got {check!r}"
    )
    # BREACH opens a challenge window rather than auto-finalizing.
    assert check["finalized"] is False
    assert check["challenge_window_ends_at"] > 0

    loan = contract.get_loan(args=[loan_id]).call()
    # _apply_consequence has already run inside trigger_covenant_check
    # (deterministic path, not gated on challenge-window close for tier1).
    assert loan["breach_tier"] == 1
    assert loan["current_interest_bps"] == 500 + 500  # base + tier1 step-up


def test_onchain_unreachable_contract_is_inconclusive(lender, borrower, require_payable):
    """source_ref points at an address with no deployed contract at all --
    a real, unhandled `gl.get_contract_at(...)` failure inside
    `_evaluate_onchain`, which must degrade to INCONCLUSIVE (never raise,
    never default to COMPLIANT/BREACH) per the trust-boundary spec."""
    contract = deploy_covenant_watch(lender)
    nonexistent = "0x" + "ab" * 20
    cov = onchain_covenant(source_ref=nonexistent, field="signer_count", op=">=", threshold=3)

    tx = contract.create_loan(
        args=[borrower.address, 2_000_000, 500, future_ts(), covenants_json(cov), 0],
    ).transact(value=1_000_000)
    assert tx_execution_succeeded(tx)
    loan_id = 0
    tx = contract.connect(borrower).lock_collateral(args=[loan_id]).transact(value=2_000_000)
    assert tx_execution_succeeded(tx)

    tx = contract.trigger_covenant_check(args=[loan_id, 0]).transact()
    assert tx_execution_succeeded(tx)

    check = contract.get_check(args=[0]).call()
    assert check["status"] == "INCONCLUSIVE", (
        f"a covenant pointed at a contract address with nothing deployed "
        f"must degrade to INCONCLUSIVE, never guess; got {check!r}"
    )
    assert check["finalized"] is True
