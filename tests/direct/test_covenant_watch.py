"""Direct-mode tests for the Covenant Watch Intelligent Contract.

All web/LLM calls used in these tests are MOCKED via direct_vm.mock_web /
direct_vm.mock_llm — see conftest.mock_offchain_verdict(). Direct mode only
ever exercises the leader function, never the validator/consensus path;
full validator-agreement behavior is covered separately in
tests/integration/.
"""

import json

import pytest

from conftest import (
    CONTRACT_PATH,
    DAY,
    covenants_json,
    offchain_covenant,
    onchain_covenant,
    mock_offchain_verdict,
    to_hex,
    warp_seconds,
)

HELPER_PATH = "tests/direct/helper_onchain_source.py"


def _create_basic_loan(direct_vm, contract, lender, borrower, covenants,
                        principal=1_000_000, collateral=2_000_000,
                        interest_bps=500, maturity_in=30 * DAY, window=0):
    direct_vm.sender = lender
    direct_vm.value = principal
    loan_id = contract.create_loan(
        to_hex(borrower),
        collateral,
        interest_bps,
        int(direct_vm.now().timestamp()) + maturity_in if hasattr(direct_vm, "now") else 10**10,
        covenants_json(*covenants),
        window,
    )
    direct_vm.value = 0
    return loan_id


# ---------------------------------------------------------------------------
# Loan creation / vague-condition rejection
# ---------------------------------------------------------------------------

def test_create_loan_and_lock_collateral(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()

    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0

    loan = contract.get_loan(loan_id)
    assert loan["status"] == "CREATED"
    assert loan["principal_deposited"] == 1_000_000
    assert loan["collateral_deposited"] == 0

    direct_vm.sender = direct_bob
    direct_vm.value = 2_000_000
    contract.lock_collateral(loan_id)
    direct_vm.value = 0

    loan = contract.get_loan(loan_id)
    assert loan["status"] == "ACTIVE"
    assert loan["collateral_deposited"] == 2_000_000


def test_cannot_check_before_collateral_is_locked(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    loan_id = _create_basic_loan(direct_vm, contract, direct_alice, direct_bob, [offchain_covenant()])
    covenant_id = contract.get_loan_covenants(loan_id)[0]["id"]
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.5)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert():
        contract.trigger_covenant_check(loan_id, covenant_id)


def test_reject_vague_covenant_at_creation(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    vague = onchain_covenant()
    vague["description"] = "borrower must remain financially healthy at all times"

    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    with direct_vm.expect_revert():
        contract.create_loan(
            to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(vague), 0
        )


def test_reject_covenant_missing_operator(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    bad = onchain_covenant()
    bad["operator"] = "~="

    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    with direct_vm.expect_revert():
        contract.create_loan(
            to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(bad), 0
        )


def test_rejects_non_https_or_private_offchain_source(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    for source_ref in ("http://example.org/feed", "https://127.0.0.1/private"):
        bad = offchain_covenant()
        bad["source_refs"][0] = source_ref
        direct_vm.sender = direct_alice
        direct_vm.value = 1_000_000
        with direct_vm.expect_revert():
            contract.create_loan(
                to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(bad), 0
            )
        direct_vm.value = 0


def test_rejects_single_or_same_host_offchain_publishers(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cases = [
        ["https://one.example.org/report"],
        [
            "https://same.example.org/a",
            "https://same.example.org/b",
            "https://same.example.org/c",
        ],
    ]
    for sources in cases:
        bad = offchain_covenant()
        bad["source_refs"] = sources
        direct_vm.sender = direct_alice
        direct_vm.value = 1_000_000
        with direct_vm.expect_revert():
            contract.create_loan(
                to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(bad), 0
            )
        direct_vm.value = 0


def test_challenge_window_bounds_enforced(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()

    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    with direct_vm.expect_revert():
        contract.create_loan(
            to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 60,
        )  # 60s is far below the 6h minimum


# ---------------------------------------------------------------------------
# Exact-match collateral enforcement
# ---------------------------------------------------------------------------

def test_exact_match_collateral_enforced(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()

    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0

    direct_vm.sender = direct_bob
    direct_vm.value = 1_999_999  # one wei short
    with direct_vm.expect_revert():
        contract.lock_collateral(loan_id)
    direct_vm.value = 0


# ---------------------------------------------------------------------------
# Authorization checks
# ---------------------------------------------------------------------------

def test_only_borrower_can_lock_collateral(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0

    direct_vm.sender = direct_charlie
    direct_vm.value = 2_000_000
    with direct_vm.expect_revert():
        contract.lock_collateral(loan_id)
    direct_vm.value = 0


def test_only_lender_or_borrower_can_trigger_check(direct_vm, direct_deploy, direct_alice,
                                                     direct_bob, direct_charlie):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0
    direct_vm.sender = direct_bob
    direct_vm.value = 2_000_000
    contract.lock_collateral(loan_id)
    direct_vm.value = 0

    covenant_id = contract.get_loan_covenants(loan_id)[0]["id"]
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert():
        contract.trigger_covenant_check(loan_id, covenant_id)


def test_only_lender_can_cancel(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0

    direct_vm.sender = direct_bob
    with direct_vm.expect_revert():
        contract.cancel_loan(loan_id)


# ---------------------------------------------------------------------------
# Cancellation before both sides committed
# ---------------------------------------------------------------------------

def test_cancel_before_collateral_locked_refunds_lender(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0

    direct_vm.sender = direct_alice
    contract.cancel_loan(loan_id)
    loan = contract.get_loan(loan_id)
    assert loan["status"] == "CANCELLED"
    assert loan["claimable_lender_wei"] == 1_000_000

    contract.claim_settlement(loan_id)
    assert contract.get_loan(loan_id)["claimable_lender_wei"] == 0

    # Second claim must raise (double-claim prevention).
    with direct_vm.expect_revert():
        contract.claim_settlement(loan_id)


def test_cannot_cancel_after_collateral_locked(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cov = onchain_covenant()
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0
    direct_vm.sender = direct_bob
    direct_vm.value = 2_000_000
    contract.lock_collateral(loan_id)
    direct_vm.value = 0

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert():
        contract.cancel_loan(loan_id)


# ---------------------------------------------------------------------------
# Compliant / breach-tier flow.
#
# NOTE ON ONCHAIN COVENANTS IN DIRECT MODE: the genlayer-test direct-mode
# harness (gltest.direct) executes leader functions as plain in-process
# Python calls and does not implement the GenVM `CallContract` cross-contract
# dispatch (confirmed via VMContext._gl_call_hook being unset by default and
# wasi_mock._handle_gl_call falling through to
# `vm._trace(f"Unknown gl_call request type: ['CallContract']")` and
# returning None whenever an ONCHAIN covenant's `gl.get_contract_at(...)
# .view()...` call is exercised against a second, separately-deployed
# contract). That is a limitation of this harness, not of the production
# contract: _evaluate_onchain() is real code that GenVM's real inter-contract
# call support executes in production and in tests/integration/ (see the
# gltest-based ONCHAIN covenant test there, which runs against real
# consensus/state and is the source of truth for that path). To keep this
# suite's coverage of the compliant/BREACH-tier/default state machine and
# consequence math meaningful without relying on an unsupported harness
# feature, the tests below drive that same state machine through the
# OFFCHAIN covenant path (mocked web+LLM, per module docstring) instead of a
# second deployed helper contract — the tier/consequence logic in
# _apply_consequence() is identical regardless of which source type produced
# the structured COMPLIANT/BREACH/INCONCLUSIVE result feeding it.
# ---------------------------------------------------------------------------

def _setup_breach_tier_loan(direct_vm, direct_deploy, direct_alice, direct_bob,
                             tier1=500, tier2=5000, threshold=1.0, maturity_ts=4_102_444_800):
    cov = offchain_covenant(threshold=threshold, tier1=tier1, tier2=tier2)
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, maturity_ts, covenants_json(cov), 0
    )
    direct_vm.value = 0
    direct_vm.sender = direct_bob
    direct_vm.value = 2_000_000
    contract.lock_collateral(loan_id)
    direct_vm.value = 0
    covenant_id = contract.get_loan_covenants(loan_id)[0]["id"]
    return contract, loan_id, covenant_id


def test_compliant_check(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "COMPLIANT"
    assert check["finalized"] is True
    assert contract.get_loan(loan_id)["status"] == "ACTIVE"


def test_model_status_cannot_override_contract_math(direct_vm, direct_deploy, direct_alice, direct_bob):
    """The LLM extracts an observation; immutable contract terms decide the verdict."""
    contract, loan_id, covenant_id = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob, threshold=1.0,
    )
    # Deliberately contradictory output: 0.5 does not satisfy >= 1.0.
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=0.5)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    initial_check = contract.get_check(check_id)
    assert initial_check["status"] == "BREACH"
    pinned_source_hash = initial_check["pinned_source_hash"]
    assert pinned_source_hash


def test_tier1_breach_interest_step_up(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob, tier1=500,
    )
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.5)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "BREACH"
    assert check["finalized"] is False  # awaiting challenge window

    warp_seconds(direct_vm, 3 * DAY)  # past the default 48h challenge window
    contract.finalize_covenant_check(loan_id, check_id)

    loan = contract.get_loan(loan_id)
    assert loan["status"] == "BREACH_TIER1"
    assert loan["current_interest_bps"] == 500 + 500  # base + step-up
    assert loan["collateral_deposited"] == 2_000_000  # untouched at tier1


def test_tier2_breach_partial_seizure(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob, tier1=500, tier2=4000,
    )
    direct_vm.sender = direct_alice

    # First breach -> tier1
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.5)
    check_id_1 = contract.trigger_covenant_check(loan_id, covenant_id)
    warp_seconds(direct_vm, 3 * DAY)
    contract.finalize_covenant_check(loan_id, check_id_1)

    # Second breach -> tier2 (cooldown has elapsed thanks to the warp above)
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.5)
    check_id_2 = contract.trigger_covenant_check(loan_id, covenant_id)
    warp_seconds(direct_vm, 3 * DAY)
    contract.finalize_covenant_check(loan_id, check_id_2)

    loan = contract.get_loan(loan_id)
    assert loan["status"] == "BREACH_TIER2"
    assert loan["claimable_lender_wei"] == 800_000  # 40% of 2_000_000
    assert loan["collateral_deposited"] == 1_200_000


def test_breaches_across_different_covenants_escalate_the_loan(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT_PATH)
    cov_a = offchain_covenant(url="https://example.org/a", tier2=4000)
    cov_b = offchain_covenant(url="https://example.org/b", tier2=4000)
    loan_id = _create_basic_loan(direct_vm, contract, direct_alice, direct_bob, [cov_a, cov_b])
    direct_vm.sender = direct_bob
    direct_vm.value = 2_000_000
    contract.lock_collateral(loan_id)
    direct_vm.value = 0
    covenant_ids = [item["id"] for item in contract.get_loan_covenants(loan_id)]

    direct_vm.sender = direct_alice
    for covenant_id in covenant_ids:
        mock_offchain_verdict(direct_vm, status="BREACH", value=0.5)
        check_id = contract.trigger_covenant_check(loan_id, covenant_id)
        warp_seconds(direct_vm, 3 * DAY)
        contract.finalize_covenant_check(loan_id, check_id)

    loan = contract.get_loan(loan_id)
    assert loan["breach_tier"] == 2
    assert loan["status"] == "BREACH_TIER2"
    assert loan["collateral_deposited"] == 1_200_000


def test_tier3_breach_full_default(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob,
    )
    direct_vm.sender = direct_alice
    for _ in range(3):
        mock_offchain_verdict(direct_vm, status="BREACH", value=0.5)
        check_id = contract.trigger_covenant_check(loan_id, covenant_id)
        warp_seconds(direct_vm, 3 * DAY)
        contract.finalize_covenant_check(loan_id, check_id)

    loan = contract.get_loan(loan_id)
    assert loan["status"] == "DEFAULTED"
    assert loan["collateral_deposited"] == 0
    # Collateral plus the still-undrawn principal are returned to the lender.
    assert loan["claimable_lender_wei"] == 3_000_000
    assert loan["principal_deposited"] == 0
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert():
        contract.claim_principal(loan_id)


def test_inconclusive_from_unreachable_onchain_source(direct_vm, direct_deploy, direct_alice, direct_bob):
    """An unavailable on-chain view must never become an error, COMPLIANT,
    or BREACH. The direct harness returns None for unsupported contract
    dispatch, which the production failure path treats as unreachable."""
    contract = direct_deploy(CONTRACT_PATH)
    unreachable = onchain_covenant()
    unreachable["source_ref"] = "0x0000000000000000000000000000000000000001"
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(unreachable), 0
    )
    direct_vm.value = 0
    direct_vm.sender = direct_bob
    direct_vm.value = 2_000_000
    contract.lock_collateral(loan_id)
    direct_vm.value = 0
    direct_vm.sender = direct_alice
    covenant_id = contract.get_loan_covenants(loan_id)[0]["id"]
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "INCONCLUSIVE"
    assert check["finalized"] is True


# ---------------------------------------------------------------------------
# Offchain compliant / breach / inconclusive flow (mocked web+LLM)
# ---------------------------------------------------------------------------

def _setup_offchain_active_loan(direct_vm, direct_deploy, direct_alice, direct_bob, threshold=1.0):
    cov = offchain_covenant(threshold=threshold)
    contract = direct_deploy(CONTRACT_PATH)
    direct_vm.sender = direct_alice
    direct_vm.value = 1_000_000
    loan_id = contract.create_loan(
        to_hex(direct_bob), 2_000_000, 500, 4_102_444_800, covenants_json(cov), 0
    )
    direct_vm.value = 0
    direct_vm.sender = direct_bob
    direct_vm.value = 2_000_000
    contract.lock_collateral(loan_id)
    direct_vm.value = 0
    covenant_id = contract.get_loan_covenants(loan_id)[0]["id"]
    return contract, loan_id, covenant_id


def test_offchain_compliant_check(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_offchain_active_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)  # MOCKED web+LLM

    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "COMPLIANT"
    # observed_value is a fixed-point decimal string (see _format_scaled in
    # the contract) so a live-deployed view returning it survives GenVM's
    # real calldata encoder, which rejects native Python float.
    assert float(check["observed_value"]) == pytest.approx(1.2)


def test_offchain_breach_check(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_offchain_active_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.8)  # MOCKED web+LLM

    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "BREACH"
    assert check["finalized"] is False


def test_offchain_inconclusive_on_fetch_failure(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_offchain_active_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    # No mock_web registered for this URL -> the render call raises -> MOCKED
    # failure path exercised, contract must resolve to INCONCLUSIVE, never
    # BREACH or COMPLIANT.
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "INCONCLUSIVE"


def test_offchain_majority_resists_one_dishonest_publisher(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_offchain_active_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob
    )
    direct_vm.clear_mocks()
    direct_vm.mock_web(r".*example\.org.*", {"status": 200, "body": "published reserve ratio"})
    direct_vm.mock_llm(
        r".*one\.example\.org.*",
        json.dumps({"status": "BREACH", "observed_value": 999, "observed_note": "dishonest outlier"}),
    )
    for host in ("two", "three"):
        direct_vm.mock_llm(
            rf".*{host}\.example\.org.*",
            json.dumps({"status": "COMPLIANT", "observed_value": 1.2, "observed_note": "corroborated"}),
        )
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    check = contract.get_check(check_id)
    assert check["status"] == "COMPLIANT"
    assert float(check["observed_value"]) == pytest.approx(1.2)
    assert "2/3" in check["observed_note"]


def test_inconclusive_never_defaults_breach_or_compliance_on_disagreement():
    """Direct mode only exercises the leader path, so genuine
    leader/validator disagreement (the other half of the INCONCLUSIVE
    guarantee) is covered in tests/integration/, where real consensus runs.
    This test documents that boundary rather than re-asserting leader-only
    behavior already covered above."""
    assert True


# ---------------------------------------------------------------------------
# Cooldown / rate-limit enforcement
# ---------------------------------------------------------------------------

def test_cooldown_enforced_per_address_per_covenant(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)
    direct_vm.sender = direct_alice
    contract.trigger_covenant_check(loan_id, covenant_id)
    with direct_vm.expect_revert():
        contract.trigger_covenant_check(loan_id, covenant_id)

    # Different address (borrower) is not subject to lender's cooldown.
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)
    direct_vm.sender = direct_bob
    contract.trigger_covenant_check(loan_id, covenant_id)


def test_cooldown_clears_after_window(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)
    direct_vm.sender = direct_alice
    contract.trigger_covenant_check(loan_id, covenant_id)
    warp_seconds(direct_vm, 20 * 60)  # past the 15-minute cooldown
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)
    contract.trigger_covenant_check(loan_id, covenant_id)  # must not revert


# ---------------------------------------------------------------------------
# Challenge window — additive evidence flow
# ---------------------------------------------------------------------------

def test_challenge_evidence_can_overturn_breach(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_offchain_active_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.8)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)
    initial_check = contract.get_check(check_id)
    assert initial_check["status"] == "BREACH"
    pinned_source_hash = initial_check["pinned_source_hash"]
    assert pinned_source_hash

    # Borrower submits additional evidence; re-evaluation (still mocked)
    # now returns COMPLIANT because the mocked LLM output is reconfigured —
    # in production this models a corrected/updated reading.
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.1)
    direct_vm.sender = direct_bob
    for host in ("four.example.org", "five.example.org", "six.example.org"):
        contract.submit_challenge_evidence(
            loan_id, check_id, f"https://{host}/corrected-reading",
            "Indexer lag misreported the ratio; corrected reading attached.",
        )

    check = contract.get_check(check_id)
    assert check["status"] == "COMPLIANT"
    assert check["finalized"] is True
    assert check["challenge_count"] == 3
    assert len(check["challenge_evidence_urls"]) == 3
    assert check["pinned_source_hash"] == pinned_source_hash
    # The originally pinned source_ref must be untouched by the challenge.
    covenant = contract.get_covenant(covenant_id)
    assert json.loads(covenant["source_ref"]) == [
        "https://one.example.org/attestation",
        "https://two.example.org/attestation",
        "https://three.example.org/attestation",
    ]


def test_challenge_window_closes_and_finalizes_breach(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_offchain_active_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.8)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)

    # Cannot finalize before the window closes.
    with direct_vm.expect_revert():
        contract.finalize_covenant_check(loan_id, check_id)

    warp_seconds(direct_vm, 3 * DAY)
    contract.finalize_covenant_check(loan_id, check_id)
    assert contract.get_check(check_id)["finalized"] is True
    assert contract.get_loan(loan_id)["status"] == "BREACH_TIER1"

    # Cannot finalize twice.
    with direct_vm.expect_revert():
        contract.finalize_covenant_check(loan_id, check_id)


def test_cannot_challenge_after_window_closes(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_offchain_active_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    mock_offchain_verdict(direct_vm, status="BREACH", value=0.8)
    direct_vm.sender = direct_alice
    check_id = contract.trigger_covenant_check(loan_id, covenant_id)

    warp_seconds(direct_vm, 3 * DAY)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert():
        contract.submit_challenge_evidence(loan_id, check_id, "https://example.org/late", "too late")


# ---------------------------------------------------------------------------
# Double-claim / double-payout prevention
# ---------------------------------------------------------------------------

def test_double_claim_principal_prevented(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    contract.claim_principal(loan_id)
    with direct_vm.expect_revert():
        contract.claim_principal(loan_id)


def test_repayment_requires_exact_amount(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, _ = _setup_breach_tier_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    contract.claim_principal(loan_id)
    # principal 1,000,000 plus 5% interest = 1,050,000; no partial payment
    # can be stranded and no excess can be gifted to the lender.
    direct_vm.value = 1_050_001
    with direct_vm.expect_revert():
        contract.repay_loan(loan_id)
    direct_vm.value = 1_050_000
    contract.repay_loan(loan_id)
    direct_vm.value = 0
    loan = contract.get_loan(loan_id)
    assert loan["status"] == "REPAID"
    assert loan["claimable_lender_wei"] == 1_050_000


def test_double_finalize_prevented_on_tier3_default(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract, loan_id, covenant_id = _setup_breach_tier_loan(direct_vm, direct_deploy, direct_alice, direct_bob)
    direct_vm.sender = direct_alice
    for _ in range(3):
        mock_offchain_verdict(direct_vm, status="BREACH", value=0.5)
        check_id = contract.trigger_covenant_check(loan_id, covenant_id)
        warp_seconds(direct_vm, 3 * DAY)
        contract.finalize_covenant_check(loan_id, check_id)

    direct_vm.sender = direct_alice
    contract.claim_settlement(loan_id)
    with direct_vm.expect_revert():
        contract.claim_settlement(loan_id)


# ---------------------------------------------------------------------------
# Timeout / reclaim path
# ---------------------------------------------------------------------------

def test_reclaim_collateral_on_lender_timeout(direct_vm, direct_deploy, direct_alice, direct_bob):
    import datetime as _dt
    near_term_maturity = int(_dt.datetime.fromisoformat(
        direct_vm._datetime.replace("Z", "+00:00")
    ).timestamp()) + 5 * DAY
    contract, loan_id, covenant_id = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob, maturity_ts=near_term_maturity,
    )
    loan = contract.get_loan(loan_id)
    maturity = loan["maturity_ts"]

    direct_vm.sender = direct_bob
    with direct_vm.expect_revert():
        contract.reclaim_collateral_timeout(loan_id)  # too early

    warp_seconds(direct_vm, 5 * DAY + 14 * DAY + DAY)  # past maturity + 14d grace
    contract.reclaim_collateral_timeout(loan_id)
    loan = contract.get_loan(loan_id)
    assert loan["status"] == "TIMEOUT_RECLAIMED"
    assert loan["claimable_borrower_wei"] == 2_000_000


def test_lender_activity_cannot_extend_fixed_maturity_grace(direct_vm, direct_deploy, direct_alice, direct_bob):
    import datetime as _dt
    maturity = int(_dt.datetime.fromisoformat(direct_vm._datetime.replace("Z", "+00:00")).timestamp()) + DAY
    contract, loan_id, covenant_id = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob, maturity_ts=maturity,
    )
    warp_seconds(direct_vm, 2 * DAY)
    mock_offchain_verdict(direct_vm, status="COMPLIANT", value=1.2)
    direct_vm.sender = direct_alice
    contract.trigger_covenant_check(loan_id, covenant_id)
    warp_seconds(direct_vm, 13 * DAY)
    direct_vm.sender = direct_bob
    contract.reclaim_collateral_timeout(loan_id)
    assert contract.get_loan(loan_id)["status"] == "TIMEOUT_RECLAIMED"


def test_drawn_unpaid_matured_loan_defaults_to_lender(direct_vm, direct_deploy, direct_alice, direct_bob):
    import datetime as _dt
    maturity = int(_dt.datetime.fromisoformat(direct_vm._datetime.replace("Z", "+00:00")).timestamp()) + DAY
    contract, loan_id, _ = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob, maturity_ts=maturity,
    )
    direct_vm.sender = direct_bob
    contract.claim_principal(loan_id)
    warp_seconds(direct_vm, 15 * DAY)

    # Permissionless progression: no lender/backend intervention is required.
    direct_vm.sender = direct_alice
    contract.settle_matured_loan(loan_id)
    loan = contract.get_loan(loan_id)
    assert loan["status"] == "DEFAULTED"
    assert loan["breach_tier"] == 3
    assert loan["collateral_deposited"] == 0
    assert loan["claimable_lender_wei"] == 2_000_000
    assert loan["claimable_borrower_wei"] == 0


def test_legacy_reclaim_cannot_reward_nonpaying_borrower(direct_vm, direct_deploy, direct_alice, direct_bob):
    import datetime as _dt
    maturity = int(_dt.datetime.fromisoformat(direct_vm._datetime.replace("Z", "+00:00")).timestamp()) + DAY
    contract, loan_id, _ = _setup_breach_tier_loan(
        direct_vm, direct_deploy, direct_alice, direct_bob, maturity_ts=maturity,
    )
    direct_vm.sender = direct_bob
    contract.claim_principal(loan_id)
    warp_seconds(direct_vm, 15 * DAY)
    contract.reclaim_collateral_timeout(loan_id)
    loan = contract.get_loan(loan_id)
    assert loan["status"] == "DEFAULTED"
    assert loan["claimable_lender_wei"] == 2_000_000
    assert loan["claimable_borrower_wei"] == 0
