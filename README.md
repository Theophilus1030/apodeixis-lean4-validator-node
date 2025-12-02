# Apodeixis Validator Node 🏛️

> **The Decentralized Oracle for Formal Verification.**

Apodeixis is a decentralized network that validates **Lean4** mathematical proofs. By running a Validator Node, you contribute computational power to verify formal theorems and earn **APDX** tokens as rewards.

This repository contains the official **Python Client (TUI)** and the **Docker Environment** required to join the network.

Our website：apodeixis.net

-----

## ✨ Key Features

  * **🛡️ Secure Isolation**: All verification tasks run inside a standardized, sandboxed Docker container to ensure determinism and safety.
  * **🚫 Anti-Cheat System**: Built-in `CheckAxioms` mechanism automatically detects and rejects proofs that use `sorry`, `admit`, or illegal axioms.
  * **🖥️ Interactive TUI**: A beautiful, retro-style Terminal User Interface (TUI) to monitor node status, logs, and earnings in real-time.
  * **💰 DeFi Integration**: Built-in wallet management to Stake, Unstake, and Claim rewards directly from the console.
  * **🤖 Auto-Settlement**: Optional "Greedy Mode" to automatically finalize tasks and claim rewards when the reveal window closes.

-----

## 📋 Prerequisites

Before you start, ensure your system meets the following requirements:

### Hardware

  * **CPU**: 2+ Cores (4+ recommended for heavy Lean4 compilations)
  * **RAM**: 8 GB+ (Lean4 compilation is memory-intensive)
  * **Disk**: 20 GB free space

### Software

  * **OS**: Ubuntu 22.04+, macOS, or Windows (via **WSL2**)
  * **Python**: Version 3.10 or higher
  * **Docker**: Docker Engine must be installed and running.

### Blockchain

  * **Wallet**: An Ethereum wallet (e.g., MetaMask) private key.
  * **Gas**: Some **Sepolia ETH** to pay for transaction fees.
  * **RPC Endpoint**: A valid Sepolia RPC URL (e.g., from [Alchemy](https://www.alchemy.com/) or [Infura](https://www.infura.io/)).

-----

## 🚀 Installation

### 1\. Clone the Repository

```bash
git clone https://github.com/Theophilus1030/apodeixis-validator-node.git
cd apodeixis-validator-node
```

### 2\. Install Python Dependencies

Enter the client directory and install the required packages:

```bash
cd client
pip install -r requirements.txt
```

### 3\. Prepare Docker Image

The node relies on a specific Docker image containing the Lean4 compiler and Mathlib.

**Option A: Pull from Docker Hub (Recommended)**

```bash
# Pull the official image
docker pull theoiphilus1030/apodeixis-validator:latest
```

**Option B: Build Locally (For Advanced Users)**

```bash
cd ../docker
docker build -t apodeixis-validator:v0.12 .
```

-----

## ⚙️ Configuration

1.  Copy the example configuration file:

    ```bash
    cd ../client
    cp .env.example .env
    ```

2.  Edit `.env` with your details:

    ```ini
    # Your Sepolia RPC URL (Get one from Alchemy/Infura)
    RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_API_KEY

    # Your Wallet Private Key (WITHOUT the 0x prefix)
    # Ensure this wallet has Sepolia ETH for gas!
    PRIVATE_KEY=abcdef123456...

    # Smart Contract Addresses (Official Sepolia Deployment)
    # Replace these with the current active contract addresses
    TOKEN_ADDRESS=0x...
    CONTRACT_ADDRESS=0x...

    # Docker Image Name
    DOCKER_IMAGE=theoiphilus1030/apodeixis-validator:latest

    # Optional: IPFS Gateway (e.g., your Pinata dedicated gateway)
    # PINATA_GATEWAY=your-gateway.mypinata.cloud
    ```

-----

## 🖥️ Usage

Start the Validator Node TUI:

```bash
python tui_app.py
```

### Interface Guide

1.  **Dashboard**: The top panel shows your RPC status, Wallet Address, APDX Balance, and Docker status. Press `r` to refresh.
2.  **Start Node**:
      * Click **[Start Node]** to begin.
      * The node will automatically **Approve** the contract and **Register** (Stake 100 APDX) if you haven't already.
      * It will then start listening for new tasks on the blockchain.
3.  **Modes**:
      * **💤 Passive Mode**: The node submits proofs but waits for others to trigger the final settlement.
      * **🔥 Greedy Mode**: The node attempts to trigger the `finalizeTask` transaction as soon as the time window allows, claiming the gas reimbursement + reward.
4.  **Funds Management**:
      * **+ Stake**: Increase your staked APDX to gain more weight in the network.
      * **- Stake**: Withdraw free APDX to your wallet.
      * **EXIT NET**: Completely unstake and exit the validator network.

### Troubleshooting

  * **Docker Error: `Permission Denied`**
      * If you are on Linux/WSL2, ensure your user is in the `docker` group:
        ```bash
        sudo usermod -aG docker $USER
        newgrp docker
        ```
  * **Transaction Failed: `Insufficient Balance`**
      * You need **Sepolia ETH** for gas fees. Go to a faucet (e.g., Google Cloud Web3 Faucet) to get some.
      * You also need **APDX** to stake. The node will try to claim from the faucet automatically, or you can visit the [Apodeixis Web Faucet](https://www.google.com/search?q=https://apodeixis.net/faucet).

-----

## 🏗️ Architecture

1.  **Listener**: The Python client listens for `TaskCreated` events on the Sepolia smart contract.
2.  **Downloader**: It fetches the `.lean` source code via IPFS.
3.  **Verifier**: It spins up an isolated Docker container to compile the code.
      * If compilation fails -\> Returns Error Hash.
      * If `sorry` or illegal axioms are detected -\> Returns Cheat Hash.
      * If successful -\> Returns Deterministic Hash.
4.  **Committer**: The node submits a `Commitment` (Hash + Salt) to the chain.
5.  **Revealer**: After the commit phase, it reveals the result to achieve consensus.

-----

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.