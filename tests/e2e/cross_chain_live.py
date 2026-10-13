"""Live Base half of the cross-chain Covenant Watch E2E.

The paired GenLayer writes are performed with the GenLayer CLI. This helper
creates matching Base loans, funds/stakes the deterministic borrower wallets,
and later settles scenario 1 after the finalized GenLayer decision is relayed.
It deliberately writes evidence only to a caller-selected JSON file; the
frontend reads the backend/indexed contracts, never this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from web3 import Web3

U = 10**6
RPC = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
USDC_ADDRESS = Web3.to_checksum_address("0x036CbD53842c5426634e7929541eC2318f3dCF7e")


def account_for_scenario(w3: Web3, number: int):
    key = "0x" + hashlib.sha256(f"covenant-watch-milestone-scenario-{number}".encode()).hexdigest()
    return w3.eth.account.from_key(key)


def runtime():
    w3 = Web3(Web3.HTTPProvider(RPC))
    deployer = w3.eth.account.from_key(os.environ["DEPLOYER_PRIVATE_KEY"])
    escrow_address = Web3.to_checksum_address(os.environ["BASE_ESCROW_ADDRESS"])
    artifact = json.loads(Path("out/CovenantWatchEscrow.sol/CovenantWatchEscrow.json").read_text())
    escrow = w3.eth.contract(address=escrow_address, abi=artifact["abi"])
    usdc = w3.eth.contract(address=USDC_ADDRESS, abi=[
        {"type":"function","name":"transfer","stateMutability":"nonpayable","inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"type":"bool"}]},
        {"type":"function","name":"approve","stateMutability":"nonpayable","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"type":"bool"}]},
        {"type":"function","name":"balanceOf","stateMutability":"view","inputs":[{"name":"account","type":"address"}],"outputs":[{"type":"uint256"}]},
    ])
    return w3, deployer, escrow_address, escrow, usdc


def send(w3: Web3, account, fn=None, value=0) -> str:
    builder = fn.build_transaction if fn else lambda tx: tx
    tx = builder({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": 84532,
        "gas": 650_000,
        "gasPrice": w3.eth.gas_price,
        "value": value,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"transaction reverted: {tx_hash.hex()}")
    return tx_hash.hex()


def loan_state(escrow, loan_id: int) -> dict:
    keys = ["lender","borrower","principal","collateralRequired","principalEscrowed","collateralEscrowed","lenderClaimable","borrowerClaimable","baseInterestBps","currentInterestBps","maturity","breachTier","requiredCompliantChecks","compliantChecks","status","principalClaimed"]
    return dict(zip(keys, escrow.functions.loans(loan_id).call()))


def setup(output: Path) -> None:
    w3, deployer, escrow_address, escrow, usdc = runtime()
    scenarios = []
    for number in (1, 2, 3):
        borrower = account_for_scenario(w3, number)
        transactions = {}
        if w3.eth.get_balance(borrower.address) < w3.to_wei(0.001, "ether"):
            transactions["fundGas"] = send_native(w3, deployer, borrower.address, w3.to_wei(0.0015, "ether"))
        if usdc.functions.balanceOf(borrower.address).call() < 25 * U:
            transactions["fundUsdc"] = send(w3, deployer, usdc.functions.transfer(borrower.address, 25 * U))
        loan_id = int(escrow.functions.loanCount().call())
        send(w3, deployer, usdc.functions.approve(escrow_address, 10 * U))
        transactions["create"] = send(w3, deployer, escrow.functions.createLoan(borrower.address, 10 * U, 15 * U, 500, int(time.time()) + 30 * 86400, 1))
        send(w3, borrower, usdc.functions.approve(escrow_address, 15 * U))
        transactions["stake"] = send(w3, borrower, escrow.functions.stakeCollateral(loan_id))
        scenarios.append({"scenario": number, "loanId": loan_id, "borrower": borrower.address, "transactions": transactions})
    output.write_text(json.dumps({"escrow": escrow_address, "scenarios": scenarios}, indent=2) + "\n")
    print(output.read_text())


def send_native(w3: Web3, account, to: str, value: int) -> str:
    tx = {"to": to, "from": account.address, "value": value, "nonce": w3.eth.get_transaction_count(account.address, "pending"), "chainId": 84532, "gas": 21_000, "gasPrice": w3.eth.gas_price}
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"native transfer reverted: {tx_hash.hex()}")
    return tx_hash.hex()


def finish(output: Path) -> None:
    w3, deployer, escrow_address, escrow, usdc = runtime()
    evidence = json.loads(output.read_text())
    # Every loan must have exactly one finalized compliant decision relayed.
    for item in evidence["scenarios"]:
        state = loan_state(escrow, item["loanId"])
        if state["compliantChecks"] != 1:
            raise RuntimeError(f"loan {item['loanId']} has no relayed compliant GenLayer decision")
        item["relayedState"] = state
    first = evidence["scenarios"][0]
    borrower = account_for_scenario(w3, 1)
    first["transactions"]["draw"] = send(w3, borrower, escrow.functions.claimPrincipal(first["loanId"]))
    send(w3, borrower, usdc.functions.approve(escrow_address, 10_500_000))
    first["transactions"]["repay"] = send(w3, borrower, escrow.functions.repay(first["loanId"]))
    first["transactions"]["lenderClaim"] = send(w3, deployer, escrow.functions.claimSettlement(first["loanId"]))
    first["transactions"]["borrowerClaim"] = send(w3, borrower, escrow.functions.claimSettlement(first["loanId"]))
    for item in evidence["scenarios"]:
        item["finalState"] = loan_state(escrow, item["loanId"])
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("setup", "finish"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/covenant-watch-cross-chain.json"))
    args = parser.parse_args()
    globals()[args.phase](args.output)
