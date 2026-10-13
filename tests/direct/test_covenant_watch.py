"""Direct tests for the adjudication-only GenLayer contract.

Economic paths are tested in Foundry and live on Base Sepolia; this suite
proves GenLayer has no payment surface and retains its evidence safeguards.
"""
import json
import pytest
from conftest import CONTRACT_PATH, DAY, covenants_json, offchain_covenant, onchain_covenant, mock_offchain_verdict, to_hex

BASE_TX = "0x" + "ab" * 32

def create(contract, vm, lender, borrower, covenants, window=0):
    vm.sender = lender
    return contract.create_loan(to_hex(borrower), 1_000_000, 2_000_000, 500, 4_102_444_800, covenants_json(*covenants), window)

def activate(contract, vm, borrower, loan_id):
    vm.sender = borrower
    contract.activate_base_loan(loan_id, BASE_TX)

def test_registers_usdc_terms_without_gen_escrow(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.value = 999_999  # ignored: create_loan is not payable
    loan_id = create(contract, direct_vm, direct_alice, direct_bob, [onchain_covenant()])
    loan = contract.get_loan(loan_id)
    assert loan["principal_wei"] == 1_000_000
    assert loan["collateral_wei"] == 2_000_000
    assert loan["principal_deposited"] == 0
    assert loan["collateral_deposited"] == 0

def test_only_borrower_can_record_base_stake(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy(CONTRACT_PATH)
    loan_id = create(contract, direct_vm, direct_alice, direct_bob, [onchain_covenant()])
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert(): contract.activate_base_loan(loan_id, BASE_TX)
    activate(contract, direct_vm, direct_bob, loan_id)
    assert contract.get_loan(loan_id)["status"] == "ACTIVE"

def test_base_tx_hash_is_validated(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    loan_id = create(contract, direct_vm, direct_alice, direct_bob, [onchain_covenant()])
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert(): contract.activate_base_loan(loan_id, "not-a-hash")

def test_rejects_vague_covenant(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH); bad = onchain_covenant(); bad["description"] = "remain financially healthy"
    with direct_vm.expect_revert(): create(contract, direct_vm, direct_alice, direct_bob, [bad])

@pytest.mark.parametrize("sources", [["http://example.org/a"], ["https://same.example/a","https://same.example/b","https://same.example/c"]])
def test_rejects_unsafe_or_non_independent_publishers(direct_vm, direct_deploy, direct_alice, direct_bob, sources):
    contract = direct_deploy(CONTRACT_PATH); bad = offchain_covenant(); bad["source_refs"] = sources
    with direct_vm.expect_revert(): create(contract, direct_vm, direct_alice, direct_bob, [bad])

def test_challenge_window_bounds(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    with direct_vm.expect_revert(): create(contract, direct_vm, direct_alice, direct_bob, [onchain_covenant()], 60)

def test_offchain_compliant_adjudication(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    loan_id = create(contract, direct_vm, direct_alice, direct_bob, [offchain_covenant()]); activate(contract, direct_vm, direct_bob, loan_id)
    covenant_id = contract.get_loan_covenants(loan_id)[0]["id"]
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "COMPLIANT" and check["finalized"] is True

def test_inconclusive_never_escalates_breach(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    loan_id = create(contract, direct_vm, direct_alice, direct_bob, [offchain_covenant()]); activate(contract, direct_vm, direct_bob, loan_id)
    covenant_id = contract.get_loan_covenants(loan_id)[0]["id"]
    mock_offchain_verdict(direct_vm, status="INCONCLUSIVE", value=0)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    assert contract.get_check(check_id)["status"] == "INCONCLUSIVE"
    assert contract.get_loan(loan_id)["breach_tier"] == 0

def test_genlayer_exposes_no_payment_methods(direct_vm, direct_deploy):
    contract = direct_deploy(CONTRACT_PATH)
    for name in ("lock_collateral", "claim_principal", "repay_loan", "claim_settlement", "cancel_loan", "settle_matured_loan"):
        assert not hasattr(contract, name), f"{name} must remain Base-only"
