"""Run three live Base Sepolia milestone scenarios and emit frontend evidence.

Requires DEPLOYER_PRIVATE_KEY. The three borrower wallets are deterministic,
testnet-only accounts derived from public scenario labels; never use them on a
network carrying real value.
"""
from __future__ import annotations
import hashlib, json, os, time
from pathlib import Path
from web3 import Web3

RPC = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
ESCROW = Web3.to_checksum_address(os.environ["BASE_ESCROW_ADDRESS"])
USDC = Web3.to_checksum_address("0x036CbD53842c5426634e7929541eC2318f3dCF7e")
DEPLOYER_KEY = os.environ["DEPLOYER_PRIVATE_KEY"]
w3 = Web3(Web3.HTTPProvider(RPC))
deployer = w3.eth.account.from_key(DEPLOYER_KEY)
artifact = json.loads(Path("out/CovenantWatchEscrow.sol/CovenantWatchEscrow.json").read_text())
escrow = w3.eth.contract(address=ESCROW, abi=artifact["abi"])
erc20 = w3.eth.contract(address=USDC, abi=[
    {"type":"function","name":"transfer","stateMutability":"nonpayable","inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"type":"bool"}]},
    {"type":"function","name":"approve","stateMutability":"nonpayable","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"type":"bool"}]},
    {"type":"function","name":"balanceOf","stateMutability":"view","inputs":[{"name":"account","type":"address"}],"outputs":[{"type":"uint256"}]},
])
U = 10**6

def scenario_account(n: int):
    key = "0x" + hashlib.sha256(f"covenant-watch-milestone-scenario-{n}".encode()).hexdigest()
    return w3.eth.account.from_key(key)

def send(account, fn=None, value=0):
    tx = (fn.build_transaction if fn else lambda x: x)({
        "from": account.address, "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": 84532, "gas": 650_000, "gasPrice": w3.eth.gas_price, "value": value,
    })
    signed = account.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    if r.status != 1: raise RuntimeError(f"transaction reverted: {h.hex()}")
    return h.hex()

def state(loan_id):
    v = escrow.functions.loans(loan_id).call()
    keys = ["lender","borrower","principal","collateralRequired","principalEscrowed","collateralEscrowed","lenderClaimable","borrowerClaimable","baseInterestBps","currentInterestBps","maturity","breachTier","requiredCompliantChecks","compliantChecks","status","principalClaimed"]
    return dict(zip(keys, v))

results = []
for n in (1, 2, 3):
    borrower = scenario_account(n)
    # Ensure the scenario wallet can stake collateral and pay Base testnet gas.
    if w3.eth.get_balance(borrower.address) < w3.to_wei(0.001, "ether"):
        tx = {"to": borrower.address, "from": deployer.address, "value": w3.to_wei(0.0015,"ether"), "nonce": w3.eth.get_transaction_count(deployer.address, "pending"), "chainId":84532, "gas":21000, "gasPrice":w3.eth.gas_price}
        signed=deployer.sign_transaction(tx); h=w3.eth.send_raw_transaction(signed.raw_transaction); w3.eth.wait_for_transaction_receipt(h)
    if erc20.functions.balanceOf(borrower.address).call() < 25*U:
        send(deployer, erc20.functions.transfer(borrower.address, 25*U))
    loan_id = escrow.functions.loanCount().call()
    txs = {}
    send(deployer, erc20.functions.approve(ESCROW, 10*U))
    txs["create"] = send(deployer, escrow.functions.createLoan(borrower.address, 10*U, 15*U, 500, int(time.time()) + 30*86400, 1))
    send(borrower, erc20.functions.approve(ESCROW, 15*U))
    txs["stake"] = send(borrower, escrow.functions.stakeCollateral(loan_id))
    if n == 1:
        txs["decision"] = send(deployer, escrow.functions.applyDecision(loan_id, 1001, 0, 200, 2500))
        txs["draw"] = send(borrower, escrow.functions.claimPrincipal(loan_id))
        send(borrower, erc20.functions.approve(ESCROW, 10_500_000))
        txs["repay"] = send(borrower, escrow.functions.repay(loan_id))
        txs["lenderClaim"] = send(deployer, escrow.functions.claimSettlement(loan_id))
        txs["borrowerClaim"] = send(borrower, escrow.functions.claimSettlement(loan_id))
        title, summary = "Compliant repayment", "10 USDC principal, 15 USDC stake, 5% interest; compliant decision, draw, repayment, and both settlement claims confirmed."
    elif n == 2:
        txs["tier1"] = send(deployer, escrow.functions.applyDecision(loan_id, 2001, 1, 200, 2500))
        txs["tier2"] = send(deployer, escrow.functions.applyDecision(loan_id, 2002, 1, 200, 2500))
        title, summary = "Graduated breach", "Two unique finalized breach decisions raised interest from 5% to 7% and allocated 3.75 USDC (25%) of collateral to the lender."
    else:
        for i in range(3): txs[f"breach{i+1}"] = send(deployer, escrow.functions.applyDecision(loan_id, 3001+i, 1, 100, 2000))
        txs["lenderClaim"] = send(deployer, escrow.functions.claimSettlement(loan_id))
        title, summary = "Tier-3 default", "Three replay-protected breach decisions produced terminal default; all remaining collateral plus undrawn principal became lender claimable and was claimed."
    results.append({"scenario": n, "title": title, "summary": summary, "loanId": loan_id, "borrower": borrower.address, "transactions": txs, "finalState": state(loan_id)})

out = {"network":"Base Sepolia","chainId":84532,"escrow":ESCROW,"usdc":USDC,"runAt":time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),"scenarios":results}
Path("frontend/src/data").mkdir(parents=True, exist_ok=True)
Path("frontend/src/data/milestoneScenarios.json").write_text(json.dumps(out, indent=2)+"\n")
print(json.dumps(out, indent=2))
