"""Read the immutable live milestone transactions and emit frontend data."""
import json, os, time
from pathlib import Path
from web3 import Web3

w3=Web3(Web3.HTTPProvider(os.getenv("BASE_SEPOLIA_RPC_URL","https://sepolia.base.org")))
address=Web3.to_checksum_address(os.getenv("BASE_ESCROW_ADDRESS","0x8D9cc4Efd412cEd3c10de543a46b8390CAa8ADe7"))
artifact=json.loads(Path("out/CovenantWatchEscrow.sol/CovenantWatchEscrow.json").read_text())
c=w3.eth.contract(address=address,abi=artifact["abi"])
deployment=w3.eth.get_transaction_receipt("0xfa10de0df52a3d569fb956fa1e3ee75238c78f957574f627132ee31ad939ebfe")
events={i:{} for i in range(3)}
for event_name in ("LoanCreated","CollateralStaked","PrincipalClaimed","DecisionApplied","Repaid","SettlementClaimed"):
    for log in getattr(c.events,event_name)().get_logs(from_block=deployment.blockNumber, to_block="latest"):
        loan_id=int(log["args"]["loanId"])
        if loan_id in events:
            events[loan_id].setdefault(event_name,[]).append(log["transactionHash"].hex())
keys=["lender","borrower","principal","collateralRequired","principalEscrowed","collateralEscrowed","lenderClaimable","borrowerClaimable","baseInterestBps","currentInterestBps","maturity","breachTier","requiredCompliantChecks","compliantChecks","status","principalClaimed"]
titles=["Compliant repayment","Graduated breach","Tier-3 default"]
summaries=[
 "10 USDC principal, 15 USDC stake, 5% interest; compliant decision, principal draw, repayment, and both settlement claims confirmed.",
 "Two unique finalized breach decisions raised interest from 5% to 7% and allocated 3.75 USDC (25%) of collateral to the lender.",
 "Three replay-protected breach decisions produced terminal default; all remaining collateral plus undrawn principal became lender claimable and was claimed."
]
scenarios=[]
for i in range(3):
    raw=c.functions.loans(i).call(); state=dict(zip(keys,raw))
    scenarios.append({"scenario":i+1,"title":titles[i],"summary":summaries[i],"loanId":i,"borrower":state["borrower"],"transactions":events[i],"finalState":state})
out={"network":"Base Sepolia","chainId":84532,"escrow":address,"usdc":"0x036CbD53842c5426634e7929541eC2318f3dCF7e","deploymentTransaction":"0xfa10de0df52a3d569fb956fa1e3ee75238c78f957574f627132ee31ad939ebfe","runAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"scenarios":scenarios}
Path("frontend/src/data").mkdir(parents=True,exist_ok=True)
Path("frontend/src/data/milestoneScenarios.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,indent=2))
