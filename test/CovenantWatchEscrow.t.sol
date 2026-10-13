// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {CovenantWatchEscrow, IERC20} from "../contracts/base/CovenantWatchEscrow.sol";

interface Vm { function prank(address) external; function warp(uint256) external; function expectRevert() external; }

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
    uint256 constant U = 1e6;

    function setUp() public {
        usdc = new MockUSDC();
        escrow = new CovenantWatchEscrow(address(usdc), address(this));
        usdc.mint(lender, 10_000 * U); usdc.mint(borrower, 10_000 * U);
        vm.prank(lender); usdc.approve(address(escrow), type(uint256).max);
        vm.prank(borrower); usdc.approve(address(escrow), type(uint256).max);
    }

    function createAndStake() internal returns (uint256 id) {
        vm.prank(lender); id = escrow.createLoan(borrower, 1_000 * U, 1_500 * U, 500, uint64(block.timestamp + 30 days), 1);
        vm.prank(borrower); escrow.stakeCollateral(id);
    }

    /// Scenario 1: compliant adjudication, principal draw, exact USDC repayment, both pull claims.
    function testE2E_CompliantRepayment() public {
        uint256 id = createAndStake();
        vm.prank(borrower); vm.expectRevert(); escrow.claimPrincipal(id);
        escrow.applyDecision(id, 100, CovenantWatchEscrow.Decision.Compliant, 200, 2500);
        vm.prank(borrower); escrow.claimPrincipal(id);
        vm.prank(borrower); escrow.repay(id);
        vm.prank(lender); escrow.claimSettlement(id);
        vm.prank(borrower); escrow.claimSettlement(id);
        assert(usdc.balanceOf(lender) == 10_050 * U);
        assert(usdc.balanceOf(borrower) == 9_950 * U);
    }

    /// Scenario 2: tier-1 interest step-up then tier-2 partial collateral seizure.
    function testE2E_GraduatedBreach() public {
        uint256 id = createAndStake();
        escrow.applyDecision(id, 200, CovenantWatchEscrow.Decision.Breach, 200, 2500);
        escrow.applyDecision(id, 201, CovenantWatchEscrow.Decision.Breach, 200, 2500);
        (,,,,, uint256 collateralEscrowed, uint256 lenderClaimable,,, uint32 rate,, uint8 tier,,,,) = escrow.loans(id);
        assert(rate == 700 && tier == 2);
        assert(collateralEscrowed == 1_125 * U && lenderClaimable == 375 * U);
    }

    /// Scenario 3: replay protection plus terminal tier-3 default allocation.
    function testE2E_Tier3DefaultAndReplayGuard() public {
        uint256 id = createAndStake();
        escrow.applyDecision(id, 300, CovenantWatchEscrow.Decision.Breach, 100, 2000);
        vm.expectRevert(); escrow.applyDecision(id, 300, CovenantWatchEscrow.Decision.Breach, 100, 2000);
        escrow.applyDecision(id, 301, CovenantWatchEscrow.Decision.Breach, 100, 2000);
        escrow.applyDecision(id, 302, CovenantWatchEscrow.Decision.Breach, 100, 2000);
        (,,,, uint256 principalEscrowed, uint256 collateralEscrowed, uint256 lenderClaimable,,,,, uint8 tier,,, CovenantWatchEscrow.Status status,) = escrow.loans(id);
        assert(principalEscrowed == 0 && collateralEscrowed == 0);
        assert(lenderClaimable == 2_500 * U && tier == 3 && status == CovenantWatchEscrow.Status.Defaulted);
    }
}
