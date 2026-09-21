"""Full happy-path integration test: create_loan -> lock_collateral ->
claim_principal -> trigger_covenant_check (OFFCHAIN, real web fetch of a
local fixture URL + real LLM interpretation) -> COMPLIANT structured result
-> repay_loan -> pull-based settlement claims.

Nothing here is mocked: `gl.nondet.web.render()` performs a real HTTP GET
against the `offchain_pages_base_url` fixture server (see conftest.py), and
`gl.nondet.exec_prompt()` performs a real LLM call through whatever
provider the target network's validators are configured with. Requires
`require_payable` and `require_llm` -- see conftest.py's environment
canaries for exactly what those verify and how they skip (with a precise
reason) rather than fail when this sandbox/network can't support them.
"""

from gltest.assertions import tx_execution_succeeded

from conftest import covenants_json, deploy_covenant_watch, future_ts, offchain_covenant


def test_happy_path_offchain_compliant(lender, borrower, offchain_pages_base_url,
                                        require_payable, require_llm):
    contract = deploy_covenant_watch(lender)

    principal = 1_000_000
    collateral = 2_000_000
    url = f"{offchain_pages_base_url}/compliant"
    cov = offchain_covenant(url=url, field="reserve_ratio", op=">=", threshold=1.0)

    # ---- create_loan: lender escrows principal as call value -------------
    tx = contract.create_loan(
        args=[borrower.address, collateral, 500, future_ts(), covenants_json(cov), 0],
    ).transact(value=principal)
    assert tx_execution_succeeded(tx)
    loan_id = 0
    loan = contract.get_loan(args=[loan_id]).call()
    assert loan["status"] == "CREATED"
    assert loan["principal_deposited"] == principal

    # ---- lock_collateral: borrower escrows exact collateral ---------------
    tx = contract.connect(borrower).lock_collateral(args=[loan_id]).transact(value=collateral)
    assert tx_execution_succeeded(tx)
    loan = contract.get_loan(args=[loan_id]).call()
    assert loan["status"] == "ACTIVE"

    # ---- claim_principal: borrower draws the escrowed principal -----------
    tx = contract.connect(borrower).claim_principal(args=[loan_id]).transact()
    assert tx_execution_succeeded(tx)
    loan = contract.get_loan(args=[loan_id]).call()
    assert loan["principal_claimed"] is True

    # ---- trigger_covenant_check: REAL fetch + REAL LLM interpretation -----
    covenant_id = 0
    tx = contract.connect(lender).trigger_covenant_check(
        args=[loan_id, covenant_id],
    ).transact()
    assert tx_execution_succeeded(tx)

    check_id = 0
    check = contract.get_check(args=[check_id]).call()
    assert check["status"] == "COMPLIANT", (
        f"expected the real LLM to read reserve_ratio=1.35 >= 1.0 from the "
        f"fixture page as COMPLIANT; got {check!r}"
    )
    # A COMPLIANT finding carries no consequence and is auto-finalized.
    assert check["finalized"] is True

    loan = contract.get_loan(args=[loan_id]).call()
    assert loan["status"] == "ACTIVE"  # unaffected by a compliant check
    assert loan["breach_tier"] == 0

    # ---- repay_loan: borrower repays principal+interest, gets collateral back
    total_due = principal + (principal * loan["current_interest_bps"]) // 10_000
    tx = contract.connect(borrower).repay_loan(args=[loan_id]).transact(value=total_due)
    assert tx_execution_succeeded(tx)
    loan = contract.get_loan(args=[loan_id]).call()
    assert loan["status"] == "REPAID"

    # ---- pull-based settlement claims for both parties ---------------------
    tx = contract.connect(lender).claim_settlement(args=[loan_id]).transact()
    assert tx_execution_succeeded(tx)
    tx = contract.connect(borrower).claim_settlement(args=[loan_id]).transact()
    assert tx_execution_succeeded(tx)

    loan = contract.get_loan(args=[loan_id]).call()
    assert loan["claimable_lender_wei"] == 0
    assert loan["claimable_borrower_wei"] == 0
