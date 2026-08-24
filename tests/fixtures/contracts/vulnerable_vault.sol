// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract VulnerableVault {
    mapping(address => uint256) public balances;
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    // Reentrancy: external call before state update
    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
        balances[msg.sender] -= amount;
    }

    // Missing access control on sensitive function
    function setOwner(address newOwner) external {
        owner = newOwner;
    }

    // tx.origin misuse
    function ownerWithdrawAll() external {
        require(tx.origin == owner, "Not owner");
        payable(owner).transfer(address(this).balance);
    }
}
