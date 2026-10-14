// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @title CovenantWatchEscrow
/// @notice Base Sepolia payment layer. GenLayer adjudicates; this contract
/// authenticates the paired loan/covenant commitments and enforces frozen terms.
contract CovenantWatchEscrow {
    enum Status { Created, Active, Tier1, Tier2, Defaulted, Repaid, Cancelled, TimeoutReclaimed }
    enum Decision { Compliant, Breach, Inconclusive }

    struct Loan {
        address lender;
        address borrower;
        uint256 principal;
        uint256 collateralRequired;
        uint256 principalEscrowed;
        uint256 collateralEscrowed;
        uint256 lenderClaimable;
        uint256 borrowerClaimable;
        uint32 baseInterestBps;
        uint32 currentInterestBps;
        uint64 maturity;
        uint64 drawdownDeadline;
        uint32 settlementGrace;
        uint8 breachTier;
        uint16 covenantCount;
        uint16 compliantCovenants;
        Status status;
        bool principalClaimed;
        bytes32 commitment;
    }

    struct CovenantTerms {
        bytes32 commitment;
        uint32 tier1StepBps;
        uint32 tier2SeizureBps;
        uint256 lastCheckId;
        bool hasDecision;
        bool compliant;
    }

    IERC20 public immutable usdc;
    address public owner;
    address public relayer;
    address public decisionSigner;
    address public immutable genLayerContract;
    uint256 public loanCount;
    uint256 public constant BPS = 10_000;
    uint32 public constant MAX_INTEREST_STEP_UP_BPS = 5_000;
    uint32 public constant MAX_TIER2_SEIZURE_BPS = 8_000;
    uint16 public constant MAX_COVENANTS = 8;
    uint32 public constant MIN_SETTLEMENT_GRACE = 60;
    uint32 public constant MAX_SETTLEMENT_GRACE = 14 days;

    mapping(uint256 => Loan) public loans;
    mapping(uint256 => mapping(uint256 => CovenantTerms)) public covenantTerms;
    mapping(uint256 => mapping(uint256 => bool)) public decisionRelayed;
    bool private locked;

    event LoanCreated(uint256 indexed loanId, address indexed lender, address indexed borrower, bytes32 commitment, uint256 principal, uint256 collateral);
    event CollateralStaked(uint256 indexed loanId, address indexed borrower, uint256 amount);
    event PrincipalClaimed(uint256 indexed loanId, address indexed borrower, uint256 amount);
    event DecisionApplied(uint256 indexed loanId, uint256 indexed checkId, uint256 indexed covenantIndex, Decision decision, uint8 tier, uint256 consequenceAmount);
    event Repaid(uint256 indexed loanId, uint256 amount);
    event SettlementClaimed(uint256 indexed loanId, address indexed account, uint256 amount);
    event LoanCancelled(uint256 indexed loanId);
    event LoanTimedOut(uint256 indexed loanId, Status status);
    event RelayerUpdated(address indexed relayer);

    modifier nonReentrant() { require(!locked, "reentrant"); locked = true; _; locked = false; }
    modifier onlyOwner() { require(msg.sender == owner, "not owner"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer, "not relayer"); _; }

    constructor(address usdc_, address relayer_, address decisionSigner_, address genLayerContract_) {
        require(usdc_ != address(0) && relayer_ != address(0) && decisionSigner_ != address(0) && genLayerContract_ != address(0), "zero address");
        usdc = IERC20(usdc_);
        owner = msg.sender;
        relayer = relayer_;
        decisionSigner = decisionSigner_;
        genLayerContract = genLayerContract_;
    }

    function computeLoanCommitment(
        uint256 loanId,
        address lender,
        address borrower,
        uint256 principal,
        uint256 collateral,
        uint32 interestBps,
        uint64 maturity,
        uint64 drawdownDeadline,
        uint32 settlementGrace,
        bytes32[] calldata covenantCommitments
    ) public pure returns (bytes32) {
        bytes memory preimage = abi.encodePacked(
            "COVENANT_WATCH_LOAN_V2", loanId, lender, borrower, principal,
            collateral, interestBps, maturity, drawdownDeadline,
            settlementGrace, uint16(covenantCommitments.length)
        );
        for (uint256 i; i < covenantCommitments.length; ++i) {
            preimage = bytes.concat(preimage, covenantCommitments[i]);
        }
        return sha256(preimage);
    }

    function createLoan(
        address borrower,
        uint256 principal,
        uint256 collateral,
        uint32 interestBps,
        uint64 maturity,
        uint64 drawdownDeadline,
        uint32 settlementGrace,
        bytes32[] calldata covenantCommitments,
        uint32[] calldata tier1StepBps,
        uint32[] calldata tier2SeizureBps,
        bytes32 expectedCommitment
    ) external nonReentrant returns (uint256 loanId) {
        require(borrower != address(0) && borrower != msg.sender, "invalid borrower");
        require(principal > 0 && collateral > 0, "zero amount");
        require(interestBps <= BPS && maturity > block.timestamp, "invalid terms");
        require(drawdownDeadline > block.timestamp && drawdownDeadline <= maturity, "invalid drawdown deadline");
        require(settlementGrace >= MIN_SETTLEMENT_GRACE && settlementGrace <= MAX_SETTLEMENT_GRACE, "invalid settlement grace");
        uint256 count = covenantCommitments.length;
        require(count > 0 && count <= MAX_COVENANTS, "invalid covenant count");
        require(tier1StepBps.length == count && tier2SeizureBps.length == count, "covenant arrays mismatch");

        loanId = loanCount++;
        bytes32 commitment = computeLoanCommitment(
            loanId, msg.sender, borrower, principal, collateral, interestBps,
            maturity, drawdownDeadline, settlementGrace, covenantCommitments
        );
        require(commitment == expectedCommitment, "loan commitment mismatch");

        loans[loanId] = Loan(
            msg.sender, borrower, principal, collateral, principal, 0, 0, 0,
            interestBps, interestBps, maturity, drawdownDeadline,
            settlementGrace, 0, uint16(count), 0, Status.Created, false, commitment
        );
        for (uint256 i; i < count; ++i) {
            require(covenantCommitments[i] != bytes32(0), "empty covenant commitment");
            require(tier1StepBps[i] <= MAX_INTEREST_STEP_UP_BPS, "excessive interest step");
            require(tier2SeizureBps[i] <= MAX_TIER2_SEIZURE_BPS, "excessive seizure");
            covenantTerms[loanId][i] = CovenantTerms(
                covenantCommitments[i], tier1StepBps[i], tier2SeizureBps[i], 0, false, false
            );
        }
        require(usdc.transferFrom(msg.sender, address(this), principal), "principal transfer failed");
        emit LoanCreated(loanId, msg.sender, borrower, commitment, principal, collateral);
    }

    function stakeCollateral(uint256 loanId) external nonReentrant {
        Loan storage loan = loans[loanId];
        require(msg.sender == loan.borrower && loan.status == Status.Created, "cannot stake");
        require(block.timestamp < loan.maturity, "matured");
        loan.collateralEscrowed = loan.collateralRequired;
        loan.status = Status.Active;
        require(usdc.transferFrom(msg.sender, address(this), loan.collateralRequired), "collateral transfer failed");
        emit CollateralStaked(loanId, msg.sender, loan.collateralRequired);
    }

    /// @notice Relay a finalized GenLayer check bound to the frozen loan and covenant.
    /// Economic parameters are never supplied by the relayer; they are read from storage.
    function applyDecision(
        uint256 loanId,
        uint256 checkId,
        uint256 covenantIndex,
        Decision decision,
        bytes32 loanCommitment,
        bytes32 covenantCommitment,
        uint256 attestationDeadline,
        bytes calldata attestation
    ) external onlyRelayer {
        Loan storage loan = loans[loanId];
        require(loan.commitment == loanCommitment && loanCommitment != bytes32(0), "loan commitment mismatch");
        require(covenantIndex < loan.covenantCount, "unknown covenant");
        CovenantTerms storage terms = covenantTerms[loanId][covenantIndex];
        require(terms.commitment == covenantCommitment && covenantCommitment != bytes32(0), "covenant commitment mismatch");
        require(!decisionRelayed[loanId][checkId], "decision already relayed");
        require(!terms.hasDecision || checkId > terms.lastCheckId, "stale covenant decision");
        require(loan.status == Status.Active || loan.status == Status.Tier1 || loan.status == Status.Tier2, "terminal loan");
        require(block.timestamp <= attestationDeadline, "attestation expired");
        bytes32 payload = keccak256(abi.encode(
            address(this), block.chainid, genLayerContract, loanId, checkId,
            covenantIndex, decision, loanCommitment, covenantCommitment,
            attestationDeadline
        ));
        bytes32 signed = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", payload));
        require(_recover(signed, attestation) == decisionSigner, "invalid decision attestation");

        decisionRelayed[loanId][checkId] = true;
        terms.lastCheckId = checkId;
        terms.hasDecision = true;
        uint256 consequence;

        if (decision == Decision.Compliant) {
            if (!terms.compliant) {
                terms.compliant = true;
                loan.compliantCovenants += 1;
            }
        } else {
            if (terms.compliant) {
                terms.compliant = false;
                loan.compliantCovenants -= 1;
            }
            if (decision == Decision.Breach) {
                uint8 tier = loan.breachTier + 1;
                if (tier > 3) tier = 3;
                loan.breachTier = tier;
                if (tier == 1) {
                    require(uint256(loan.currentInterestBps) + terms.tier1StepBps <= BPS, "interest cap exceeded");
                    loan.currentInterestBps += terms.tier1StepBps;
                    loan.status = Status.Tier1;
                } else if (tier == 2) {
                    consequence = loan.collateralEscrowed * terms.tier2SeizureBps / BPS;
                    loan.collateralEscrowed -= consequence;
                    loan.lenderClaimable += consequence;
                    loan.status = Status.Tier2;
                } else {
                    consequence = loan.collateralEscrowed;
                    loan.collateralEscrowed = 0;
                    loan.lenderClaimable += consequence + loan.principalEscrowed;
                    loan.principalEscrowed = 0;
                    loan.status = Status.Defaulted;
                }
            }
        }
        emit DecisionApplied(loanId, checkId, covenantIndex, decision, loan.breachTier, consequence);
    }

    function claimPrincipal(uint256 loanId) external nonReentrant {
        Loan storage loan = loans[loanId];
        require(msg.sender == loan.borrower && !loan.principalClaimed, "cannot claim");
        require(loan.status == Status.Active || loan.status == Status.Tier1 || loan.status == Status.Tier2, "inactive");
        require(block.timestamp <= loan.drawdownDeadline, "drawdown deadline passed");
        require(loan.compliantCovenants == loan.covenantCount, "covenants incomplete");
        uint256 amount = loan.principalEscrowed;
        require(amount > 0, "nothing claimable");
        loan.principalEscrowed = 0;
        loan.principalClaimed = true;
        require(usdc.transfer(msg.sender, amount), "principal transfer failed");
        emit PrincipalClaimed(loanId, msg.sender, amount);
    }

    function repay(uint256 loanId) external nonReentrant {
        Loan storage loan = loans[loanId];
        require(msg.sender == loan.borrower && loan.principalClaimed, "cannot repay");
        require(loan.status == Status.Active || loan.status == Status.Tier1 || loan.status == Status.Tier2, "inactive");
        uint256 due = loan.principal + loan.principal * loan.currentInterestBps / BPS;
        require(usdc.transferFrom(msg.sender, address(this), due), "repayment transfer failed");
        loan.lenderClaimable += due;
        loan.borrowerClaimable += loan.collateralEscrowed;
        loan.collateralEscrowed = 0;
        loan.status = Status.Repaid;
        emit Repaid(loanId, due);
    }

    function cancel(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(msg.sender == loan.lender && loan.status == Status.Created, "cannot cancel");
        loan.lenderClaimable += loan.principalEscrowed;
        loan.principalEscrowed = 0;
        loan.status = Status.Cancelled;
        emit LoanCancelled(loanId);
    }

    function settleMatured(uint256 loanId) external {
        Loan storage loan = loans[loanId];
        require(block.timestamp >= uint256(loan.maturity) + loan.settlementGrace, "grace active");
        require(loan.status == Status.Active || loan.status == Status.Tier1 || loan.status == Status.Tier2, "not settleable");
        if (loan.principalClaimed) {
            loan.lenderClaimable += loan.collateralEscrowed;
            loan.status = Status.Defaulted;
            loan.breachTier = 3;
        } else {
            loan.lenderClaimable += loan.principalEscrowed;
            loan.borrowerClaimable += loan.collateralEscrowed;
            loan.principalEscrowed = 0;
            loan.status = Status.TimeoutReclaimed;
        }
        loan.collateralEscrowed = 0;
        emit LoanTimedOut(loanId, loan.status);
    }

    function claimSettlement(uint256 loanId) external nonReentrant {
        Loan storage loan = loans[loanId];
        uint256 amount;
        if (msg.sender == loan.lender) { amount = loan.lenderClaimable; loan.lenderClaimable = 0; }
        else if (msg.sender == loan.borrower) { amount = loan.borrowerClaimable; loan.borrowerClaimable = 0; }
        else revert("not party");
        require(amount > 0, "nothing claimable");
        require(usdc.transfer(msg.sender, amount), "settlement transfer failed");
        emit SettlementClaimed(loanId, msg.sender, amount);
    }

    function setRelayer(address next) external onlyOwner { require(next != address(0), "zero relayer"); relayer = next; emit RelayerUpdated(next); }
    function setDecisionSigner(address next) external onlyOwner { require(next != address(0), "zero signer"); decisionSigner = next; }
    function transferOwnership(address next) external onlyOwner { require(next != address(0), "zero owner"); owner = next; }

    function _recover(bytes32 digest, bytes calldata signature) private pure returns (address) {
        require(signature.length == 65, "invalid signature length");
        bytes32 r; bytes32 s; uint8 v;
        assembly { r := calldataload(signature.offset) s := calldataload(add(signature.offset, 32)) v := byte(0, calldataload(add(signature.offset, 64))) }
        if (v < 27) v += 27;
        require(v == 27 || v == 28, "invalid signature v");
        require(uint256(s) <= 0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0, "invalid signature s");
        return ecrecover(digest, v, r, s);
    }
}
