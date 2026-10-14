// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {CovenantWatchEscrow, IERC20} from "../contracts/base/CovenantWatchEscrow.sol";

interface Vm { function prank(address) external; function warp(uint256) external; function expectRevert() external; function addr(uint256) external returns (address); function sign(uint256, bytes32) external returns (uint8, bytes32, bytes32); }

contract MockUSDC is IERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }
    function approve(address spender, uint256 amount) external returns (bool) { allowance[msg.sender][spender] = amount; return true; }
    function transfer(address to, uint256 amount) external returns (bool) { balanceOf[msg.sender] -= amount; balanceOf[to] += amount; return true; }
    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        allowance[from][msg.sender] -= amount; balanceOf[from] -= amount; balanceOf[to] += amount; return true;
    }
}

contract CovenantWatchEscrowTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    MockUSDC usdc;
    CovenantWatchEscrow escrow;
    address lender = address(0x1111);
    address borrower = address(0x2222);
    address attacker = address(0x3333);
    uint256 signerKey = 0xA11CE;
    uint256 constant U = 1e6;

    function setUp() public {
        usdc = new MockUSDC();
        escrow = new CovenantWatchEscrow(address(usdc), address(this), vm.addr(signerKey), address(0x4444));
        usdc.mint(lender, 10_000 * U); usdc.mint(borrower, 10_000 * U);
        vm.prank(lender); usdc.approve(address(escrow), type(uint256).max);
        vm.prank(borrower); usdc.approve(address(escrow), type(uint256).max);
    }

    function terms(uint256 count) internal pure returns (bytes32[] memory commits, uint32[] memory steps, uint32[] memory seizures) {
        commits = new bytes32[](count); steps = new uint32[](count); seizures = new uint32[](count);
        for (uint256 i; i < count; ++i) { commits[i] = sha256(abi.encodePacked("covenant", i)); steps[i] = 200; seizures[i] = 2500; }
    }

    function createAndStake(uint256 count) internal returns (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) {
        uint32[] memory steps; uint32[] memory seizures;
        (commits, steps, seizures) = terms(count);
        id = escrow.loanCount();
        uint64 maturity = uint64(block.timestamp + 30 days);
        uint64 drawdown = uint64(block.timestamp + 7 days);
        loanCommitment = escrow.computeLoanCommitment(id, lender, borrower, 1_000 * U, 1_500 * U, 500, maturity, drawdown, 1 days, commits);
        vm.prank(lender);
        escrow.createLoan(borrower, 1_000 * U, 1_500 * U, 500, maturity, drawdown, 1 days, commits, steps, seizures, loanCommitment);
        vm.prank(borrower); escrow.stakeCollateral(id);
    }

    function relayDecision(uint256 id, uint256 checkId, uint256 covenantIndex, CovenantWatchEscrow.Decision decision, bytes32 loanCommitment, bytes32 covenantCommitment) internal {
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 payload = keccak256(abi.encode(address(escrow), block.chainid, address(0x4444), id, checkId, covenantIndex, decision, loanCommitment, covenantCommitment, deadline));
        bytes32 digest = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", payload));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerKey, digest);
        escrow.applyDecision(id, checkId, covenantIndex, decision, loanCommitment, covenantCommitment, deadline, abi.encodePacked(r, s, v));
    }

    function testDistinctCovenantsRequiredForDraw() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(2);
        relayDecision(id, 100, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
        relayDecision(id, 101, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
        vm.prank(borrower); vm.expectRevert(); escrow.claimPrincipal(id);
        relayDecision(id, 102, 1, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[1]);
        vm.prank(borrower); escrow.claimPrincipal(id);
    }

    function testLaterBreachRevokesCovenantComplianceBeforeDraw() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(1);
        relayDecision(id, 100, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
        relayDecision(id, 101, 0, CovenantWatchEscrow.Decision.Breach, loanCommitment, commits[0]);
        vm.prank(borrower); vm.expectRevert(); escrow.claimPrincipal(id);
    }

    function testPostDrawdownAndPostMaturityBorrowingRejected() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(1);
        relayDecision(id, 100, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
        vm.warp(block.timestamp + 7 days + 1);
        vm.prank(borrower); vm.expectRevert(); escrow.claimPrincipal(id);
        vm.warp(block.timestamp + 30 days);
        vm.prank(borrower); vm.expectRevert(); escrow.claimPrincipal(id);
    }

    function testForgedCommitmentsAndUnknownCovenantRejected() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(1);
        vm.expectRevert(); relayDecision(id, 1, 0, CovenantWatchEscrow.Decision.Compliant, bytes32(uint256(9)), commits[0]);
        vm.expectRevert(); relayDecision(id, 1, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, bytes32(uint256(9)));
        vm.expectRevert(); relayDecision(id, 1, 7, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
    }

    function testUnauthorizedRelayAndReplayRejected() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(1);
        vm.prank(attacker); vm.expectRevert(); escrow.applyDecision(id, 1, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0], 0, "");
        relayDecision(id, 1, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
        vm.expectRevert(); relayDecision(id, 1, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
        vm.expectRevert(); relayDecision(id, 0, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
    }

    function testAuthorizedRelayerCannotForgeSignedVerdictOrUseExpiredAttestation() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(1);
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 payload = keccak256(abi.encode(address(escrow), block.chainid, address(0x4444), id, 7, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0], deadline));
        bytes32 digest = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", payload));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerKey, digest);
        bytes memory signature = abi.encodePacked(r, s, v);
        vm.expectRevert(); escrow.applyDecision(id, 7, 0, CovenantWatchEscrow.Decision.Breach, loanCommitment, commits[0], deadline, signature);
        vm.warp(deadline + 1);
        vm.expectRevert(); escrow.applyDecision(id, 7, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0], deadline, signature);
    }

    function testExcessiveFrozenConsequencesRejectedAtOrigination() public {
        (bytes32[] memory commits, uint32[] memory steps, uint32[] memory seizures) = terms(1);
        uint64 maturity = uint64(block.timestamp + 30 days);
        uint64 drawdown = uint64(block.timestamp + 7 days);
        bytes32 commitment = escrow.computeLoanCommitment(0, lender, borrower, 1_000 * U, 1_500 * U, 500, maturity, drawdown, 1 days, commits);
        steps[0] = 5001;
        vm.prank(lender); vm.expectRevert(); escrow.createLoan(borrower, 1_000 * U, 1_500 * U, 500, maturity, drawdown, 1 days, commits, steps, seizures, commitment);
        steps[0] = 200; seizures[0] = 8001;
        vm.prank(lender); vm.expectRevert(); escrow.createLoan(borrower, 1_000 * U, 1_500 * U, 500, maturity, drawdown, 1 days, commits, steps, seizures, commitment);
    }

    function testLoanPairingMismatchRejected() public {
        (bytes32[] memory commits, uint32[] memory steps, uint32[] memory seizures) = terms(1);
        uint64 maturity = uint64(block.timestamp + 30 days);
        uint64 drawdown = uint64(block.timestamp + 7 days);
        bytes32 wrong = escrow.computeLoanCommitment(99, lender, borrower, 1_000 * U, 1_500 * U, 500, maturity, drawdown, 1 days, commits);
        vm.prank(lender); vm.expectRevert(); escrow.createLoan(borrower, 1_000 * U, 1_500 * U, 500, maturity, drawdown, 1 days, commits, steps, seizures, wrong);
    }

    function testRelayFailureRecoveryWithoutDoubleApply() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(1);
        vm.expectRevert(); relayDecision(id, 8, 0, CovenantWatchEscrow.Decision.Breach, loanCommitment, bytes32(uint256(1)));
        relayDecision(id, 8, 0, CovenantWatchEscrow.Decision.Breach, loanCommitment, commits[0]);
        (,,,,,,,,, uint32 rate,,,, uint8 tier,,,,,) = escrow.loans(id);
        assert(rate == 700 && tier == 1);
        vm.expectRevert(); relayDecision(id, 8, 0, CovenantWatchEscrow.Decision.Breach, loanCommitment, commits[0]);
    }

    function testRepaymentAndMaturitySettlementRecipients() public {
        (uint256 id, bytes32 loanCommitment, bytes32[] memory commits) = createAndStake(1);
        relayDecision(id, 100, 0, CovenantWatchEscrow.Decision.Compliant, loanCommitment, commits[0]);
        vm.prank(borrower); escrow.claimPrincipal(id);
        vm.prank(borrower); escrow.repay(id);
        vm.prank(lender); escrow.claimSettlement(id);
        vm.prank(borrower); escrow.claimSettlement(id);
        assert(usdc.balanceOf(lender) == 10_050 * U);
        assert(usdc.balanceOf(borrower) == 9_950 * U);

        (uint256 second,,) = createAndStake(1);
        vm.warp(block.timestamp + 31 days);
        escrow.settleMatured(second);
        vm.prank(lender); escrow.claimSettlement(second);
        vm.prank(borrower); escrow.claimSettlement(second);
    }
}
