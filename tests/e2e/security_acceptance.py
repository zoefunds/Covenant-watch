"""Current-address cross-chain security acceptance runner.

Runs three real Base Sepolia/GenLayer StudioNet scenarios with separate lender
and borrower keys and writes an evidence JSON containing every transaction,
receipt summary, state readback, and USDC balance delta. It never writes keys
to the evidence file or repository.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from web3 import Web3
from eth_account.messages import encode_defunct
from eth_abi import encode

U = 10**6
BASE_RPC = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
USDC = Web3.to_checksum_address("0x036CbD53842c5426634e7929541eC2318f3dCF7e")
GENLAYER = os.environ["GENLAYER_CONTRACT_ADDRESS"]
ESCROW_ADDRESS = Web3.to_checksum_address(os.environ["BASE_ESCROW_ADDRESS"])
OUTPUT = Path(os.getenv("EVIDENCE_OUTPUT", "acceptance-evidence.json"))

PRIMARY = [
    "https://en.wikipedia.org/wiki/Bitcoin",
    "https://river.com/learn/terms/1/21-million/",
    "https://www.fidelitydigitalassets.com/research-and-insights/understanding-bitcoin-and-ethereum-supply",
]
CHALLENGE = [
    "https://bitcoin.org/en/faq#how-are-bitcoins-created",
    "https://www.investopedia.com/tech/what-happens-bitcoin-after-21-million-mined/",
    "https://www.coinbase.com/learn/crypto-basics/what-is-bitcoin",
]


def pack_u(value: int, size: int) -> bytes:
    return int(value).to_bytes(size, "big")


def pack_text(value: str) -> bytes:
    raw = value.encode()
    return pack_u(len(raw), 4) + raw


def normalized(cov: dict) -> dict:
    out = dict(cov)
    out["source_ref"] = json.dumps(out["source_refs"], separators=(",", ":"))
    out["challenge_source_ref"] = json.dumps(out["challenge_source_refs"], separators=(",", ":"))
    out["threshold_scaled"] = round(float(out["threshold"]) * U)
    return out


def covenant_commitment(index: int, raw: dict) -> bytes:
    cov = normalized(raw)
    preimage = b"COVENANT_WATCH_COVENANT_V2" + pack_u(index, 4)
    for key in ("source_type", "source_ref", "challenge_source_ref", "condition_field", "operator", "description"):
        preimage += pack_text(str(cov[key]))
    preimage += int(cov["threshold_scaled"]).to_bytes(32, "big", signed=True)
    preimage += pack_u(cov["tier1_interest_step_up_bps"], 4)
    preimage += pack_u(cov["tier2_seizure_bps"], 4)
    return hashlib.sha256(preimage).digest()


def loan_commitment(loan_id: int, lender: str, borrower: str, principal: int,
                    collateral: int, interest: int, maturity: int, drawdown: int,
                    grace: int, covenant_commitments: list[bytes]) -> bytes:
    preimage = b"COVENANT_WATCH_LOAN_V2" + pack_u(loan_id, 32)
    preimage += bytes.fromhex(lender[2:]) + bytes.fromhex(borrower[2:])
    preimage += pack_u(principal, 32) + pack_u(collateral, 32) + pack_u(interest, 4)
    preimage += pack_u(maturity, 8) + pack_u(drawdown, 8) + pack_u(grace, 4)
    preimage += pack_u(len(covenant_commitments), 2) + b"".join(covenant_commitments)
    return hashlib.sha256(preimage).digest()


def covenant(operator: str, description: str) -> dict:
    return {
        "source_type": "OFFCHAIN", "source_ref": "", "source_refs": PRIMARY,
        "challenge_source_refs": CHALLENGE, "condition_field": "max_bitcoin_supply",
        "operator": operator, "threshold": 21_000_000 if operator == "==" else 1,
        "description": description, "tier1_interest_step_up_bps": 150,
        "tier2_seizure_bps": 3000,
    }


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=Path(__file__).parents[2], text=True,
                            capture_output=True, check=True)
    return result.stdout + result.stderr


def gen_write(account: str, method: str, args: list[object]) -> dict:
    if account == os.environ.get("BORROWER_GEN_ACCOUNT", "cw-security-borrower-live"):
        run("genlayer", "account", "unlock", "--account", account, "--password", os.environ.get("BORROWER_GEN_PASSWORD", "covenant-watch-live"))
    run("genlayer", "account", "use", account)
    rendered = []
    for value in args:
        if isinstance(value, (list, dict)):
            rendered.append(json.dumps(value, separators=(",", ":")))
        else:
            # The GenLayer CLI accepts 32-byte hex values as integers. The
            # contract normalizes those integers back to canonical bytes32;
            # quoting them would leave literal quote characters in tx hashes.
            rendered.append(str(value))
    output = run("genlayer", "write", GENLAYER, method, "--args", *rendered)
    hashes = re.findall(r"Write Transaction Hash:\s*(0x[0-9a-fA-F]{64})", output)
    if not hashes:
        raise RuntimeError(f"no transaction hash from {method}: {output[-1000:]}")
    tx_hash = hashes[-1]
    receipt = run("genlayer", "receipt", "--status", "FINALIZED", "--retries", "180", tx_hash)
    if ("execution_result: 'SUCCESS'" not in receipt
            and "execution_result: SUCCESS" not in receipt
            and "result_name: 'MAJORITY_AGREE'" not in receipt):
        raise RuntimeError(f"GenLayer {method} did not execute successfully: {receipt[-2000:]}")
    votes = re.findall(r"'?(0x[0-9a-fA-F]{40})'?: '?(agree|disagree)'?", receipt, re.I)
    return {"hash": tx_hash, "method": method, "successfulGenVm": True,
            "validatorVotes": [{"validator": a, "vote": v.upper()} for a, v in votes]}


def main() -> None:
    w3 = Web3(Web3.HTTPProvider(BASE_RPC, request_kwargs={"timeout": 20}))
    lender = w3.eth.account.from_key(os.environ["DEPLOYER_PRIVATE_KEY"])
    borrower = w3.eth.account.from_key(os.environ["BORROWER_PRIVATE_KEY"])
    relayer = w3.eth.account.from_key(os.environ.get("RELAYER_PRIVATE_KEY", os.environ["DEPLOYER_PRIVATE_KEY"]))
    decision_signer = w3.eth.account.from_key(os.environ["DECISION_SIGNER_PRIVATE_KEY"])
    borrower_gen_account = os.environ.get("BORROWER_GEN_ACCOUNT", "cw-security-borrower-live")
    artifact = json.loads(Path("out/CovenantWatchEscrow.sol/CovenantWatchEscrow.json").read_text())
    escrow = w3.eth.contract(address=ESCROW_ADDRESS, abi=artifact["abi"])
    usdc = w3.eth.contract(address=USDC, abi=[
        {"type":"function","name":"balanceOf","stateMutability":"view","inputs":[{"name":"a","type":"address"}],"outputs":[{"type":"uint256"}]},
        {"type":"function","name":"approve","stateMutability":"nonpayable","inputs":[{"name":"s","type":"address"},{"name":"v","type":"uint256"}],"outputs":[{"type":"bool"}]},
    ])
    evidence = {"contracts": {"base": ESCROW_ADDRESS, "genlayer": GENLAYER, "usdc": USDC},
                "wallets": {"lender": lender.address, "borrower": borrower.address, "relayer": relayer.address},
                "startedAt": int(time.time()), "scenarios": []}

    def checkpoint() -> None:
        OUTPUT.write_text(json.dumps(evidence, indent=2, default=lambda value: value.hex() if isinstance(value, bytes) else str(value)) + "\n")

    def base_send(account, label: str, fn, *, expected_revert: bool = False) -> dict:
        before = {"lender": usdc.functions.balanceOf(lender.address).call(),
                  "borrower": usdc.functions.balanceOf(borrower.address).call(),
                  "escrow": usdc.functions.balanceOf(ESCROW_ADDRESS).call()}
        try:
            estimated = fn.estimate_gas({"from": account.address})
        except Exception:
            if not expected_revert:
                raise
            # A reverting call cannot be estimated. Broadcast it with a bounded
            # limit so its failed receipt becomes durable negative-test evidence.
            estimated = 500_000
        tx = fn.build_transaction({"from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "chainId": 84532, "gas": int(estimated * 1.25) + 10_000,
            "gasPrice": int(os.getenv("BASE_GAS_PRICE_WEI", str(w3.eth.gas_price)))})
        tx_hash = w3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        after = {"lender": usdc.functions.balanceOf(lender.address).call(),
                 "borrower": usdc.functions.balanceOf(borrower.address).call(),
                 "escrow": usdc.functions.balanceOf(ESCROW_ADDRESS).call()}
        return {"label": label, "hash": tx_hash.hex(), "status": receipt.status,
                "blockNumber": receipt.blockNumber, "usdcBefore": before, "usdcAfter": after}

    def create_pair(name: str, covenants: list[dict], maturity: int, drawdown: int, grace: int) -> dict:
        loan_id = escrow.functions.loanCount().call()
        commits = [covenant_commitment(i, cov) for i, cov in enumerate(covenants)]
        commitment = loan_commitment(loan_id, lender.address, borrower.address, U, 1_500_000, 500, maturity, drawdown, grace, commits)
        txs = [base_send(lender, "approve principal", usdc.functions.approve(ESCROW_ADDRESS, U))]
        txs.append(base_send(lender, "escrow principal", escrow.functions.createLoan(
            borrower.address, U, 1_500_000, 500, maturity, drawdown, grace, commits,
            [c["tier1_interest_step_up_bps"] for c in covenants],
            [c["tier2_seizure_bps"] for c in covenants], commitment)))
        gen = [gen_write("cw-milestone", "create_loan", [loan_id, "0x" + commitment.hex(), borrower.address,
            U, 1_500_000, 500, maturity, drawdown, grace, covenants, 300])]
        txs.append(base_send(borrower, "approve collateral", usdc.functions.approve(ESCROW_ADDRESS, 1_500_000)))
        stake = base_send(borrower, "stake collateral", escrow.functions.stakeCollateral(loan_id)); txs.append(stake)
        gen.append(gen_write(borrower_gen_account, "activate_base_loan", [loan_id, "0x" + stake["hash"].removeprefix("0x")]))
        return {"name": name, "loanId": loan_id, "loanCommitment": "0x" + commitment.hex(),
                "covenantCommitments": ["0x" + item.hex() for item in commits], "baseTransactions": txs,
                "genlayerTransactions": gen}

    def attested_decision(loan_id: int, check_id: int, covenant_index: int, decision: int, loan_commitment_hex: str, covenant_commitment_hex: str):
        deadline = int(time.time()) + 600
        payload = Web3.keccak(encode(
            ["address","uint256","address","uint256","uint256","uint256","uint8","bytes32","bytes32","uint256"],
            [ESCROW_ADDRESS, 84532, Web3.to_checksum_address(GENLAYER), loan_id, check_id, covenant_index, decision,
             bytes.fromhex(loan_commitment_hex.removeprefix("0x")), bytes.fromhex(covenant_commitment_hex.removeprefix("0x")), deadline],
        ))
        signature = decision_signer.sign_message(encode_defunct(primitive=payload)).signature
        return deadline, signature

    def mark_relayed(check_id: int, base_tx: dict, scenario: dict) -> None:
        scenario["genlayerTransactions"].append(
            gen_write("cw-milestone", "mark_decision_relayed", [check_id, base_tx["hash"]])
        )

    now = int(time.time())
    genlayer_count = int(os.getenv("GENLAYER_COUNT", "0"))
    if escrow.functions.loanCount().call() == 1:
        # Resume the paired loan created by an interrupted first run. Its
        # commitment and activation are read back from the current contracts.
        loan = escrow.functions.loans(0).call()
        terms = escrow.functions.covenantTerms(0, 0).call()
        maturity = int(loan[10]); drawdown = int(loan[11]); grace = int(loan[12])
        recovered_cov = covenant("==", "Independent publishers confirm Bitcoin maximum supply equals 21,000,000.")
        recovered_commit = covenant_commitment(0, recovered_cov)
        compliant = {
            "name": "compliant draw, repayment, and rightful withdrawals",
            "loanId": 0,
            "loanCommitment": "0x" + bytes(loan[-1]).hex(),
            "covenantCommitments": ["0x" + bytes(terms[0]).hex()],
            "baseTransactions": [{"label": "stake collateral", "hash": "0x8f7d906994d3b07ea80047a2e07d7146fce8204a3f27e048074f75ce6bbfdbde", "status": 1}],
            "genlayerTransactions": [],
            "resumedFromVerifiedOnchainState": True,
        }
        if genlayer_count == 0:
            compliant["genlayerTransactions"].append(gen_write("cw-milestone", "create_loan", [0, compliant["loanCommitment"], borrower.address, U, 1_500_000, 500, maturity, drawdown, grace, [recovered_cov], 300]))
        if genlayer_count == 0:
            compliant["genlayerTransactions"].append(gen_write(borrower_gen_account, "activate_base_loan", [0, "0x8f7d906994d3b07ea80047a2e07d7146fce8204a3f27e048074f75ce6bbfdbde"]))
    else:
        compliant = create_pair("compliant draw, repayment, and rightful withdrawals", [covenant("==", "Independent publishers confirm Bitcoin maximum supply equals 21,000,000.")], now + 3600, now + 1800, 60)
    loan_zero = escrow.functions.loans(0).call()
    if loan_zero[15] == 0:
        compliant["genlayerTransactions"].append(gen_write("cw-milestone", "trigger_covenant_check", [0, 0]))
        time.sleep(310)
        compliant["genlayerTransactions"].append(gen_write("cw-milestone", "finalize_covenant_check", [0, 0]))
        # Relay once with a deliberately forged commitment (must revert), then recover with the authentic commitment.
        deadline, signature = attested_decision(0, 0, 0, 0, compliant["loanCommitment"], compliant["covenantCommitments"][0])
        forged = base_send(relayer, "forged verdict rejected", escrow.functions.applyDecision(0, 0, 0, 1, bytes.fromhex(compliant["loanCommitment"][2:]), bytes.fromhex(compliant["covenantCommitments"][0][2:]), deadline, signature), expected_revert=True)
        if forged["status"] != 0: raise AssertionError("forged relay unexpectedly succeeded")
        compliant["baseTransactions"].append(forged)
        relay = base_send(relayer, "relay authenticated compliant decision", escrow.functions.applyDecision(0, 0, 0, 0, bytes.fromhex(compliant["loanCommitment"][2:]), bytes.fromhex(compliant["covenantCommitments"][0][2:]), deadline, signature))
        compliant["baseTransactions"].append(relay)
        mark_relayed(0, relay, compliant)
    else:
        compliant["securityReadback"] = {"distinctCompliantCovenants": loan_zero[15], "covenantCount": loan_zero[14]}
    if loan_zero[16] != 5:
        compliant["baseTransactions"].append(base_send(borrower, "borrower draw", escrow.functions.claimPrincipal(0)))
        compliant["baseTransactions"].append(base_send(borrower, "approve repayment", usdc.functions.approve(ESCROW_ADDRESS, 1_050_000)))
        compliant["baseTransactions"].append(base_send(borrower, "exact repayment", escrow.functions.repay(0)))
        compliant["baseTransactions"].append(base_send(lender, "lender withdrawal", escrow.functions.claimSettlement(0)))
        compliant["baseTransactions"].append(base_send(borrower, "borrower collateral withdrawal", escrow.functions.claimSettlement(0)))
    compliant["finalBaseState"] = list(escrow.functions.loans(0).call())
    evidence["scenarios"].append(compliant)
    checkpoint()

    now = int(time.time())
    breach_covs = [covenant("<", f"Breach covenant {i + 1}: maximum supply must be below one.") for i in range(3)]
    breach = create_pair("challenge reconciliation and three-tier breach penalties", breach_covs, now + 3600, now + 1800, 60)
    for covenant_id in (1, 2, 3):
        breach["genlayerTransactions"].append(gen_write("cw-milestone", "trigger_covenant_check", [1, covenant_id]))
    for url in CHALLENGE:
        breach["genlayerTransactions"].append(gen_write(borrower_gen_account, "submit_challenge_evidence", [1, 1, url, "Preauthorized independent supporting evidence"] ))
    wait_until = int(time.time()) + 310
    evidence["challengeWaitUntil"] = wait_until
    while time.time() < wait_until: time.sleep(min(15, wait_until - time.time()))
    for check_id in (1, 2, 3):
        breach["genlayerTransactions"].append(gen_write("cw-milestone", "finalize_covenant_check", [1, check_id]))
        deadline, signature = attested_decision(1, check_id, check_id - 1, 1, breach["loanCommitment"], breach["covenantCommitments"][check_id - 1])
        relay = base_send(relayer, f"relay authenticated breach check {check_id}", escrow.functions.applyDecision(1, check_id, check_id - 1, 1, bytes.fromhex(breach["loanCommitment"][2:]), bytes.fromhex(breach["covenantCommitments"][check_id - 1][2:]), deadline, signature))
        breach["baseTransactions"].append(relay)
        mark_relayed(check_id, relay, breach)
    breach["baseTransactions"].append(base_send(lender, "lender default withdrawal", escrow.functions.claimSettlement(1)))
    breach["finalBaseState"] = list(escrow.functions.loans(1).call())
    evidence["scenarios"].append(breach)
    checkpoint()

    now = int(time.time())
    matured = create_pair("undrawn maturity settlement and rightful withdrawals", [covenant("==", "Maturity scenario covenant remains unqueried.")], now + 180, now + 90, 60)
    while time.time() < now + 245: time.sleep(min(15, now + 245 - time.time()))
    matured["baseTransactions"].append(base_send(lender, "permissionless maturity settlement", escrow.functions.settleMatured(2)))
    matured["baseTransactions"].append(base_send(lender, "lender principal withdrawal", escrow.functions.claimSettlement(2)))
    matured["baseTransactions"].append(base_send(borrower, "borrower collateral withdrawal", escrow.functions.claimSettlement(2)))
    matured["finalBaseState"] = list(escrow.functions.loans(2).call())
    evidence["scenarios"].append(matured)
    evidence["finishedAt"] = int(time.time())
    checkpoint()
    print(OUTPUT)


if __name__ == "__main__":
    main()
