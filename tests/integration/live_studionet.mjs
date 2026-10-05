import fs from "node:fs";
import { createAccount, createClient, chains } from "../../frontend/node_modules/genlayer-js/dist/index.js";
import { ExecutionResult, TransactionStatus } from "../../frontend/node_modules/genlayer-js/dist/types/index.js";
import * as Keystore from "../../frontend/node_modules/ox/_esm/core/Keystore.js";
import keytar from "/opt/homebrew/lib/node_modules/genlayer/node_modules/keytar/lib/keytar.js";

const address = process.env.CONTRACT_ADDRESS;
const lenderKeystore = process.env.LENDER_KEYSTORE;
const borrowerKeystore = process.env.BORROWER_KEYSTORE;
const password = process.env.KEYSTORE_PASSWORD;
const sourceBases = (process.env.OFFCHAIN_BASE_URLS ?? "").split(",").filter(Boolean);
const explicitSources = (process.env.SOURCE_URLS ?? "").split(",").filter(Boolean);
const endpoint = process.env.GENLAYER_RPC_URL;

if (!address || (sourceBases.length !== 3 && explicitSources.length !== 3)) {
  throw new Error("CONTRACT_ADDRESS and exactly three OFFCHAIN_BASE_URLS or SOURCE_URLS are required");
}

const decryptAccount = async (path, accountName) => {
  const key = path && password
    ? Keystore.decrypt(JSON.parse(fs.readFileSync(path, "utf8")), password)
    : await keytar.getPassword("genlayer-cli", `account:${accountName}`);
  if (!key) throw new Error(`GenLayer test account ${accountName} is not unlocked in the OS keychain`);
  return createAccount(key);
};

const lender = await decryptAccount(lenderKeystore, process.env.LENDER_ACCOUNT ?? "cw-lender-e2e");
const borrower = await decryptAccount(borrowerKeystore, process.env.BORROWER_ACCOUNT ?? "cw-borrower-e2e");
const lenderClient = createClient({ chain: chains.studionet, account: lender, ...(endpoint ? { endpoint } : {}) });
const borrowerClient = createClient({ chain: chains.studionet, account: borrower, ...(endpoint ? { endpoint } : {}) });

const requireSuccess = async (client, hash, label) => {
  const receipt = await client.waitForTransactionReceipt({
    hash,
    status: TransactionStatus.FINALIZED,
    fullTransaction: false,
    retries: 240,
    interval: 3000,
  });
  const execution = receipt.txExecutionResultName ?? receipt.executionResultName;
  const executionNumber = receipt.txExecutionResult ?? receipt.executionResult;
  const statusName = receipt.statusName ?? receipt.status_name;
  const finalized = statusName === "FINALIZED" || receipt.status === 7;
  const leaderReceipts = receipt.consensusData?.leaderReceipt ?? receipt.consensus_data?.leader_receipt ?? [];
  const leaderExecution = leaderReceipts[0]?.executionResult ?? leaderReceipts[0]?.execution_result;
  const executionSucceeded =
    execution === "FINISHED_WITH_RETURN" ||
    executionNumber === ExecutionResult.FINISHED_WITH_RETURN ||
    leaderExecution === "SUCCESS";
  if (
    !finalized ||
    !executionSucceeded
  ) {
    throw new Error(`${label} finalized unsuccessfully: ${JSON.stringify({ statusName, status: receipt.status, execution, executionNumber, leaderExecution, keys: Object.keys(receipt) })}`);
  }
  return receipt;
};

const write = async (client, functionName, args = [], value = 0n) => {
  const hash = await client.writeContract({ address, functionName, args, value });
  return requireSuccess(client, hash, functionName);
};

const read = (client, functionName, args = []) =>
  client.readContract({ address, functionName, args, stateStatus: "finalized" });

const waitFor = async (description, probe, predicate, attempts = 40) => {
  let last;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    last = await probe();
    if (predicate(last)) return last;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  throw new Error(`timed out waiting for ${description}: ${JSON.stringify(last)}`);
};

const before = Number(await read(lenderClient, "get_loan_count"));
const principal = 1_000_000n;
const collateral = 2_000_000n;
const covenant = {
  source_type: "OFFCHAIN",
  source_ref: "",
  source_refs: explicitSources.length === 3
    ? explicitSources
    : sourceBases.map((base) => `${base}/evidence/compliant`),
  condition_field: process.env.CONDITION_FIELD ?? "reserve_ratio",
  operator: process.env.OPERATOR ?? ">=",
  threshold: Number(process.env.THRESHOLD ?? "1"),
  description: process.env.COVENANT_DESCRIPTION ?? "Independent publishers must corroborate reserve_ratio at or above 1.0.",
  tier1_interest_step_up_bps: 500,
  tier2_seizure_bps: 5000,
};
const maturity = Math.floor(Date.now() / 1000) + 30 * 24 * 60 * 60;

const resumeLoanId = process.env.RESUME_LOAN_ID;
const loanId = resumeLoanId === undefined ? before : Number(resumeLoanId);
if (resumeLoanId === undefined) {
  await write(
    lenderClient,
    "create_loan",
    [borrower.address, Number(collateral), 500, maturity, JSON.stringify([covenant]), 6 * 60 * 60],
    principal,
  );
}

let loan = await read(lenderClient, "get_loan", [loanId]);
const loanCovenants = await read(lenderClient, "get_loan_covenants", [loanId]);
const covenantId = Number(loanCovenants[0].id);
if (loan.status === "CREATED") {
  await write(borrowerClient, "lock_collateral", [loanId], collateral);
  loan = await read(lenderClient, "get_loan", [loanId]);
}
const priorChecks = await read(lenderClient, "get_check_history", [loanId]);
let triggerReceipt;
if (priorChecks.length === 0) {
  triggerReceipt = await write(lenderClient, "trigger_covenant_check", [loanId, covenantId]);
}

const checkHistory = await waitFor(
  "finalized check history",
  () => read(lenderClient, "get_check_history", [loanId]),
  (history) => history.length > 0,
);
const checkId = Number(checkHistory[checkHistory.length - 1].id);
const check = await read(lenderClient, "get_check", [checkId]);
if (check.status !== "COMPLIANT" || check.finalized !== true) {
  throw new Error(`live covenant check was not compliant and finalized: ${JSON.stringify(check)}`);
}
if (!String(check.observed_note).includes("2/3") && !String(check.observed_note).includes("3/3")) {
  throw new Error(`live check did not record publisher corroboration: ${JSON.stringify(check)}`);
}

const votes = triggerReceipt?.consensusData?.votes ?? triggerReceipt?.consensus_data?.votes ?? {};
const agreeing = Object.values(votes).filter((vote) => String(vote).toLowerCase() === "agree").length;
if (triggerReceipt && agreeing < 2) {
  throw new Error(`expected genuine multi-validator agreement, got ${JSON.stringify(votes)}`);
}

loan = await read(lenderClient, "get_loan", [loanId]);
if (!loan.principal_claimed) {
  const drawReady = await read(lenderClient, "can_claim_principal", [loanId]);
  if (drawReady !== true) throw new Error(`principal draw was not enabled after finalized compliant checks`);
  await write(borrowerClient, "claim_principal", [loanId]);
  loan = await read(lenderClient, "get_loan", [loanId]);
}
if (loan.status !== "REPAID") {
  const totalDue = principal + (principal * BigInt(loan.current_interest_bps)) / 10_000n;
  await write(borrowerClient, "repay_loan", [loanId], totalDue);
}
loan = await read(lenderClient, "get_loan", [loanId]);
if (BigInt(loan.claimable_lender_wei) > 0n) await write(lenderClient, "claim_settlement", [loanId]);
if (BigInt(loan.claimable_borrower_wei) > 0n) await write(borrowerClient, "claim_settlement", [loanId]);

const finalLoan = await read(lenderClient, "get_loan", [loanId]);
if (finalLoan.status !== "REPAID" || Number(finalLoan.claimable_lender_wei) !== 0 || Number(finalLoan.claimable_borrower_wei) !== 0) {
  throw new Error(`live escrow lifecycle did not settle cleanly: ${JSON.stringify(finalLoan)}`);
}

console.log(JSON.stringify({
  ok: true,
  contract: address,
  loanId,
  checkStatus: check.status,
  observedValue: check.observed_value,
  observedNote: check.observed_note,
  agreeingValidators: agreeing,
  finalLoanStatus: finalLoan.status,
}));
