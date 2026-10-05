import fs from "node:fs";
import { createAccount, createClient, chains } from "../../frontend/node_modules/genlayer-js/dist/index.js";
import { ExecutionResult, TransactionStatus } from "../../frontend/node_modules/genlayer-js/dist/types/index.js";
import * as Keystore from "../../frontend/node_modules/ox/_esm/core/Keystore.js";
// Contract calls stay on the v1 client because this deployed v1 contract's
// calldata codec is not wire-compatible with v2.  v2 is used only for the
// protocol-level appeal API, whose safe operation atomically quotes, funds,
// and binds an appeal to the active consensus decision.
import {
  createAccount as createAppealAccount,
  createClient as createAppealClient,
  chains as appealChains,
} from "./node_modules/genlayer-js-v2/dist/index.js";
import keytar from "/opt/homebrew/lib/node_modules/genlayer/node_modules/keytar/lib/keytar.js";

const address = process.env.CONTRACT_ADDRESS;
const lenderKeystore = process.env.LENDER_KEYSTORE;
const borrowerKeystore = process.env.BORROWER_KEYSTORE;
const password = process.env.KEYSTORE_PASSWORD;
const sourceBases = (process.env.OFFCHAIN_BASE_URLS ?? "").split(",").filter(Boolean);
const explicitSources = (process.env.SOURCE_URLS ?? "").split(",").filter(Boolean);
const challengeSources = (process.env.CHALLENGE_SOURCE_URLS ?? "").split(",").filter(Boolean);
const endpoint = process.env.GENLAYER_RPC_URL;
const runChallenge = process.env.RUN_CHALLENGE === "1";
const runAppeal = process.env.RUN_APPEAL === "1";

if (!address || (sourceBases.length !== 3 && explicitSources.length !== 3)) {
  throw new Error("CONTRACT_ADDRESS and exactly three OFFCHAIN_BASE_URLS or SOURCE_URLS are required");
}
if (runChallenge && challengeSources.length !== 3) {
  throw new Error("RUN_CHALLENGE=1 requires exactly three CHALLENGE_SOURCE_URLS");
}
if (runAppeal && !runChallenge) {
  throw new Error("RUN_APPEAL=1 requires RUN_CHALLENGE=1 so the appeal covers the nondeterministic reevaluation");
}

const decryptKey = async (path, accountName) => {
  const key = path && password
    ? Keystore.decrypt(JSON.parse(fs.readFileSync(path, "utf8")), password)
    : await keytar.getPassword("genlayer-cli", `account:${accountName}`);
  if (!key) throw new Error(`GenLayer test account ${accountName} is not unlocked in the OS keychain`);
  return key;
};

const lenderKey = await decryptKey(lenderKeystore, process.env.LENDER_ACCOUNT ?? "cw-lender-e2e");
const borrowerKey = await decryptKey(borrowerKeystore, process.env.BORROWER_ACCOUNT ?? "cw-borrower-e2e");
const lender = createAccount(lenderKey);
const borrower = createAccount(borrowerKey);
const lenderClient = createClient({ chain: chains.studionet, account: lender, ...(endpoint ? { endpoint } : {}) });
const borrowerClient = createClient({ chain: chains.studionet, account: borrower, ...(endpoint ? { endpoint } : {}) });
const lenderAppealClient = createAppealClient({ chain: appealChains.studionet, account: createAppealAccount(lenderKey) });

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

const waitForAccepted = async (client, hash, label) => {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    const tx = await client.getTransaction({ hash });
    const status = tx.statusName ?? tx.status_name ?? tx.status;
    if (status === "ACCEPTED" || status === 5) return tx;
    if (status === "FINALIZED" || status === 7) {
      throw new Error(`${label} finalized before an appeal could be submitted`);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`timed out waiting for ${label} to become appealable`);
};

const writeAndAppeal = async (client, functionName, args = [], value = 0n) => {
  const hash = await client.writeContract({ address, functionName, args, value });
  await waitForAccepted(client, hash, functionName);
  const charge = await lenderAppealClient.getAppealCharge({ txId: hash });
  const cap = process.env.MAX_APPEAL_CHARGE_WEI;
  if (cap !== undefined && charge > BigInt(cap)) {
    throw new Error(`appeal charge ${charge} exceeds MAX_APPEAL_CHARGE_WEI=${cap}`);
  }
  await lenderAppealClient.appealTransaction({ txId: hash, value: charge });
  const finalized = await requireSuccess(client, hash, `${functionName} (appealed)`);
  return { finalized, appealCharge: charge };
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
let check = await read(lenderClient, "get_check", [checkId]);
let challengeReceipt;
let appealCharge = 0n;

if (runChallenge) {
  if (check.status !== "BREACH" || check.finalized === true || Number(check.challenge_window_ends_at) <= 0) {
    throw new Error(`initial challenge fixture did not produce an open BREACH: ${JSON.stringify(check)}`);
  }
  const initialSourceHash = check.result_source_hash;
  for (let index = 0; index < challengeSources.length; index += 1) {
    const args = [loanId, checkId, challengeSources[index], `Independent publisher ${index + 1} corroborates the corrected value.`];
    if (index === challengeSources.length - 1 && runAppeal) {
      const appealed = await writeAndAppeal(lenderClient, "submit_challenge_evidence", args);
      challengeReceipt = appealed.finalized;
      appealCharge = appealed.appealCharge;
    } else {
      challengeReceipt = await write(lenderClient, "submit_challenge_evidence", args);
    }
  }
  check = await read(lenderClient, "get_check", [checkId]);
  if (check.status !== "COMPLIANT" || check.finalized !== true || Number(check.challenge_count) !== 3) {
    throw new Error(`challenge did not overturn the breach with a finalized compliant result: ${JSON.stringify(check)}`);
  }
  if (check.result_source_hash === initialSourceHash) {
    throw new Error("challenge reevaluation did not bind a distinct evidence-source hash");
  }
} else if (check.status !== "COMPLIANT" || check.finalized !== true) {
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
const challengeVotes = challengeReceipt?.consensusData?.votes ?? challengeReceipt?.consensus_data?.votes ?? {};
const challengeAgreeing = Object.values(challengeVotes).filter((vote) => String(vote).toLowerCase() === "agree").length;
if (runChallenge && challengeAgreeing < 2) {
  throw new Error(`expected genuine multi-validator agreement on challenge reevaluation, got ${JSON.stringify(challengeVotes)}`);
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
  challenge: runChallenge ? {
    overturnedBreach: true,
    evidencePublishers: Number(check.challenge_count),
    agreeingValidators: challengeAgreeing,
    appealed: runAppeal,
    appealCharge: appealCharge.toString(),
  } : undefined,
  finalLoanStatus: finalLoan.status,
}));
