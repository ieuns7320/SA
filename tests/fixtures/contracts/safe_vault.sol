// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

// vulnerable_vault.sol과 동일한 목적이지만 방어 로직이 제대로 갖춰진 버전.
// LLM의 오탐 필터링(false_positive 판정)이 실제로 작동하는지 검증하는 fixture.
contract SafeVault {
    mapping(address => uint256) public balances;
    address public owner;
    bool private locked;

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier nonReentrant() {
        require(!locked, "Reentrant call");
        locked = true;
        _;
        locked = false;
    }

    constructor() {
        owner = msg.sender;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    // checks-effects-interactions 패턴 + nonReentrant 가드
    function withdraw(uint256 amount) external nonReentrant {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        balances[msg.sender] -= amount;
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
    }

    function setOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        owner = newOwner;
    }

    function ownerWithdrawAll() external onlyOwner {
        payable(owner).transfer(address(this).balance);
    }
}
