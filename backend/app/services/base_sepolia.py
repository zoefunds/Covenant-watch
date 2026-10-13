"""Base Sepolia payment-layer client.

GenLayer is read for evidence decisions; this module is the narrow bridge that
submits a *finalized* decision to the USDC escrow. It never receives user funds
or signs on a user's behalf.
"""
from __future__ import annotations

from web3 import Web3

from app.core.config import get_settings

ESCROW_ABI = [
    {"type":"function","name":"applyDecision","stateMutability":"nonpayable","inputs":[
        {"name":"loanId","type":"uint256"},{"name":"checkId","type":"uint256"},
        {"name":"covenantIndex","type":"uint256"},{"name":"decision","type":"uint8"},
        {"name":"loanCommitment","type":"bytes32"},{"name":"covenantCommitment","type":"bytes32"}],"outputs":[]},
    {"type":"function","name":"loans","stateMutability":"view","inputs":[{"name":"","type":"uint256"}],
     "outputs":[{"name":"lender","type":"address"},{"name":"borrower","type":"address"},
        {"name":"principal","type":"uint256"},{"name":"collateralRequired","type":"uint256"},
        {"name":"principalEscrowed","type":"uint256"},{"name":"collateralEscrowed","type":"uint256"},
        {"name":"lenderClaimable","type":"uint256"},{"name":"borrowerClaimable","type":"uint256"},
        {"name":"baseInterestBps","type":"uint32"},{"name":"currentInterestBps","type":"uint32"},
        {"name":"maturity","type":"uint64"},{"name":"drawdownDeadline","type":"uint64"},
        {"name":"settlementGrace","type":"uint32"},{"name":"breachTier","type":"uint8"},
        {"name":"covenantCount","type":"uint16"},{"name":"compliantCovenants","type":"uint16"},
        {"name":"status","type":"uint8"},{"name":"principalClaimed","type":"bool"},
        {"name":"commitment","type":"bytes32"}]},
    {"type":"function","name":"decisionRelayed","stateMutability":"view","inputs":[
        {"name":"","type":"uint256"},{"name":"","type":"uint256"}],"outputs":[{"type":"bool"}]},
]

def _web3() -> Web3:
    return Web3(Web3.HTTPProvider(get_settings().BASE_SEPOLIA_RPC_URL))

def get_base_loan(loan_id: int) -> dict:
    settings = get_settings()
    if not settings.BASE_ESCROW_ADDRESS:
        raise RuntimeError("BASE_ESCROW_ADDRESS is not configured")
    w3 = _web3()
    values = w3.eth.contract(address=Web3.to_checksum_address(settings.BASE_ESCROW_ADDRESS), abi=ESCROW_ABI).functions.loans(loan_id).call()
    names = ["lender","borrower","principal","collateral_required","principal_escrowed","collateral_escrowed","lender_claimable","borrower_claimable","base_interest_bps","current_interest_bps","maturity","drawdown_deadline","settlement_grace","breach_tier","covenant_count","compliant_covenants","status","principal_claimed","commitment"]
    loan = dict(zip(names, values))
    # web3 returns bytes32 values as HexBytes. FastAPI's generic encoder treats
    # bytes as UTF-8 text, which fails for arbitrary commitment hashes and
    # turns an otherwise successful contract read into a 500 response.
    commitment = loan.get("commitment")
    if isinstance(commitment, (bytes, bytearray)):
        loan["commitment"] = Web3.to_hex(commitment)
    return loan

def relay_finalized_decision(loan_id: int, check_id: int, covenant_index: int, decision: int, loan_commitment: str, covenant_commitment: str) -> str:
    settings = get_settings()
    if not settings.BASE_ESCROW_ADDRESS or not settings.BASE_RELAYER_PRIVATE_KEY:
        raise RuntimeError("Base Sepolia relay is not configured")
    w3 = _web3()
    account = w3.eth.account.from_key(settings.BASE_RELAYER_PRIVATE_KEY)
    contract = w3.eth.contract(address=Web3.to_checksum_address(settings.BASE_ESCROW_ADDRESS), abi=ESCROW_ABI)
    gas_price = w3.eth.gas_price
    priority_fee = min(w3.to_wei(1, "gwei"), gas_price)
    tx = contract.functions.applyDecision(loan_id, check_id, covenant_index, decision, loan_commitment, covenant_commitment).build_transaction({
        "from": account.address, "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": 84532, "gas": 350_000, "maxFeePerGas": gas_price * 2 + priority_fee,
        "maxPriorityFeePerGas": priority_fee,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"Base decision relay reverted: {tx_hash.hex()}")
    return tx_hash.hex()

def is_decision_relayed(loan_id: int, check_id: int) -> bool:
    settings = get_settings()
    if not settings.BASE_ESCROW_ADDRESS:
        return False
    w3 = _web3()
    contract = w3.eth.contract(address=Web3.to_checksum_address(settings.BASE_ESCROW_ADDRESS), abi=ESCROW_ABI)
    return bool(contract.functions.decisionRelayed(loan_id, check_id).call())
