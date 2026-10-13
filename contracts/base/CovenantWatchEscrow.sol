// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @title CovenantWatchEscrow
/// @notice Base Sepolia is the only payment and staking layer for Covenant Watch.
/// GenLayer adjudicates public evidence; an authorized relayer submits only the
/// finalized decision here. All amounts are six-decimal USDC base units.
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
        uint8 breachTier;
        uint16 requiredCompliantChecks;
        uint16 compliantChecks;
        Status status;
        bool principalClaimed;
    }

    IERC20 public immutable usdc;
    address public owner;
    address public relayer;
    uint256 public loanCount;
    uint256 public constant BPS = 10_000;
    uint256 public constant MATURITY_GRACE = 14 days;

    mapping(uint256 => Loan) public loans;
    mapping(uint256 => mapping(uint256 => bool)) public decisionRelayed;
    bool private locked;

    event LoanCreated(uint256 indexed loanId, address indexed lender, address indexed borrower, uint256 principal, uint256 collateral);
    event CollateralStaked(uint256 indexed loanId, address indexed borrower, uint256 amount);
    event PrincipalClaimed(uint256 indexed loanId, address indexed borrower, uint256 amount);
    event DecisionApplied(uint256 indexed loanId, uint256 indexed checkId, Decision decision, uint8 tier, uint256 consequenceAmount);
    event Repaid(uint256 indexed loanId, uint256 amount);
    event SettlementClaimed(uint256 indexed loanId, address indexed account, uint256 amount);
    event LoanCancelled(uint256 indexed loanId);
    event LoanTimedOut(uint256 indexed loanId, Status status);
    event RelayerUpdated(address indexed relayer);

    modifier nonReentrant() { require(!locked, "reentrant"); locked = true; _; locked = false; }
    modifier onlyOwner() { require(msg.sender == owner, "not owner"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer, "not relayer"); _; }

    constructor(address usdc_, address relayer_) {
        require(usdc_ != address(0) && relayer_ != address(0), "zero address");
        usdc = IERC20(usdc_);
        owner = msg.sender;
        relayer = relayer_;
    }

    function createLoan(address borrower, uint256 principal, uint256 collateral, uint32 interestBps, uint64 maturity, uint16 requiredCompliantChecks)
        external nonReentrant returns (uint256 loanId)
    {
        require(borrower != address(0) && borrower != msg.sender, "invalid borrower");
        require(principal > 0 && collateral > 0, "zero amount");
        require(interestBps <= BPS && maturity > block.timestamp && requiredCompliantChecks > 0, "invalid terms");
        loanId = loanCount++;
        loans[loanId] = Loan(msg.sender, borrower, principal, collateral, principal, 0, 0, 0,
            interestBps, interestBps, maturity, 0, requiredCompliantChecks, 0, Status.Created, false);
        require(usdc.transferFrom(msg.sender, address(this), principal), "principal transfer failed");
        emit LoanCreated(loanId, msg.sender, borrower, principal, collateral);
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

    /// @notice Called only after the corresponding GenLayer check is final.
    function applyDecision(uint256 loanId, uint256 checkId, Decision decision, uint32 tier1StepBps, uint32 tier2SeizureBps)
        external onlyRelayer
    {
        Loan storage loan = loans[loanId];
        require(!decisionRelayed[loanId][checkId], "decision already relayed");
        require(loan.status == Status.Active || loan.status == Status.Tier1 || loan.status == Status.Tier2, "terminal loan");
        require(tier2SeizureBps <= BPS, "invalid seizure");
        decisionRelayed[loanId][checkId] = true;
        uint256 consequence;
        if (decision == Decision.Compliant) {
            require(loan.compliantChecks < loan.requiredCompliantChecks, "compliance already satisfied");
            loan.compliantChecks += 1;
        } else if (decision == Decision.Breach) {
            uint8 tier = loan.breachTier + 1;
            if (tier > 3) tier = 3;
            loan.breachTier = tier;
            if (tier == 1) {
                require(uint256(loan.currentInterestBps) + tier1StepBps <= type(uint32).max, "interest overflow");
                loan.currentInterestBps += tier1StepBps;
                loan.status = Status.Tier1;
            } else if (tier == 2) {
                consequence = loan.collateralEscrowed * tier2SeizureBps / BPS;
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
        emit DecisionApplied(loanId, checkId, decision, loan.breachTier, consequence);
    }

    function claimPrincipal(uint256 loanId) external nonReentrant {
        Loan storage loan = loans[loanId];
        require(msg.sender == loan.borrower && !loan.principalClaimed, "cannot claim");
        require(loan.status == Status.Active || loan.status == Status.Tier1 || loan.status == Status.Tier2, "inactive");
        require(loan.compliantChecks >= loan.requiredCompliantChecks, "compliance checks incomplete");
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
        require(block.timestamp >= uint256(loan.maturity) + MATURITY_GRACE, "grace active");
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
    function transferOwnership(address next) external onlyOwner { require(next != address(0), "zero owner"); owner = next; }
}
