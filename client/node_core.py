import os
import json
import asyncio
import re
from typing import Callable
from pathlib import Path

import httpx
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

# [Adaptation] Dynamically load Web3 middleware
try:
    from web3.middleware import ExtraDataToPOAMiddleware
    PoAMiddleware = ExtraDataToPOAMiddleware
except ImportError:
    from web3.middleware import geth_poa_middleware
    PoAMiddleware = geth_poa_middleware

# ================= ABI Definitions =================
ERC20_ABI = json.loads('[{"constant":false,"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"}, {"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}, {"constant":false,"inputs":[],"name":"faucet","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"}, {"constant":true,"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}]')

MAIN_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"_stakeAmount","type":"uint256"}],"name":"registerValidator","outputs":[],"stateMutability":"nonpayable","type":"function"}, {"inputs":[{"internalType":"uint256","name":"_amount","type":"uint256"}],"name":"increaseStake","outputs":[],"stateMutability":"nonpayable","type":"function"}, {"inputs":[{"internalType":"uint256","name":"_amount","type":"uint256"}],"name":"decreaseStake","outputs":[],"stateMutability":"nonpayable","type":"function"}, {"inputs":[],"name":"exitNetwork","outputs":[],"stateMutability":"nonpayable","type":"function"}, {"inputs":[{"internalType":"uint256","name":"_taskId","type":"uint256"},{"internalType":"bytes32","name":"_commitment","type":"bytes32"}],"name":"commitResult","outputs":[],"stateMutability":"nonpayable","type":"function"}, {"inputs":[{"internalType":"uint256","name":"_taskId","type":"uint256"},{"internalType":"bytes32","name":"_result","type":"bytes32"},{"internalType":"bytes32","name":"_salt","type":"bytes32"}],"name":"revealResult","outputs":[],"stateMutability":"nonpayable","type":"function"}, {"inputs":[{"internalType":"uint256","name":"_taskId","type":"uint256"}],"name":"finalizeTask","outputs":[],"stateMutability":"nonpayable","type":"function"}, {"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"taskId","type":"uint256"},{"indexed":false,"internalType":"string","name":"ipfsCID","type":"string"},{"indexed":false,"internalType":"uint256","name":"reward","type":"uint256"}],"name":"TaskCreated","type":"event"}, {"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"validators","outputs":[{"internalType":"uint256","name":"stake","type":"uint256"},{"internalType":"uint256","name":"reputation","type":"uint256"},{"internalType":"bool","name":"isActive","type":"bool"},{"internalType":"bool","name":"isRegistered","type":"bool"}],"stateMutability":"view","type":"function"}, {"inputs":[{"internalType":"uint256","name":"","type":"uint256"}],"name":"tasks","outputs":[{"internalType":"address","name":"creator","type":"address"},{"internalType":"string","name":"ipfsCID","type":"string"},{"internalType":"uint256","name":"reward","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bool","name":"finalized","type":"bool"},{"internalType":"bytes32","name":"consensusResult","type":"bytes32"}],"stateMutability":"view","type":"function"}]')

class ValidatorNode:
    def __init__(self, log_callback: Callable[[str, str], None], greedy: bool = False):
        self.log = log_callback
        self.running = False
        self.greedy_mode = greedy
        
        self.rpc_url = os.getenv("RPC_URL", "http://127.0.0.1:8545")
        self.private_key = os.getenv("PRIVATE_KEY")
        self.token_addr = os.getenv("TOKEN_ADDRESS")
        self.contract_addr = os.getenv("CONTRACT_ADDRESS")
        self.docker_image = os.getenv("DOCKER_IMAGE", "apodeixis-validator:v0.12")
        self.pinata_gateway = os.getenv("PINATA_GATEWAY")
        
        os.environ.pop("http_proxy", None)
        os.environ.pop("https_proxy", None)
        
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.w3.middleware_onion.inject(PoAMiddleware, layer=0)
        
        if self.private_key:
            self.account = Account.from_key(self.private_key)
            self.log(f"Loaded account: {self.account.address[:10]}...", "INFO")
        
        self.token = self.w3.eth.contract(address=self.token_addr, abi=ERC20_ABI)
        self.main_contract = self.w3.eth.contract(address=self.contract_addr, abi=MAIN_ABI)

    async def start(self):
        self.running = True
        mode_str = "🔥 GREEDY" if self.greedy_mode else "💤 PASSIVE"
        self.log(f"Node engine starting ({mode_str})...", "INFO")
        
        try:
            await self._ensure_registration()
            self.log("Entering event loop...", "INFO")
            await self._event_loop()
        except Exception as e:
            self.log(f"Fatal Error: {str(e)}", "ERROR")
            self.running = False

    def stop(self):
        self.running = False
        self.log("Stopping node engine...", "WARN")

    def toggle_greedy(self):
        self.greedy_mode = not self.greedy_mode
        status = "ENABLED" if self.greedy_mode else "DISABLED"
        self.log(f"Greedy Mode {status}", "WARN")
        return self.greedy_mode

    # ================= [Fix] Fund Management Methods =================

    async def increase_stake(self, amount_apdx: float):
        """Increase stake"""
        amount_wei = self.w3.to_wei(amount_apdx, 'ether')
        self.log(f"Increasing stake by {amount_apdx} APDX...", "INFO")
        
        # Check allowance
        allowance = await asyncio.to_thread(
            self.token.functions.allowance(self.account.address, self.contract_addr).call
        )
        if allowance < amount_wei:
            self.log("Insufficient allowance. Approving...", "WARN")
            await self._send_tx(self.token.functions.approve(self.contract_addr, amount_wei))
        
        # Send transaction
        receipt = await self._send_tx(self.main_contract.functions.increaseStake(amount_wei))
        
        # [Fix] Get transactionHash from receipt
        tx_hash_hex = receipt['transactionHash'].hex()
        self.log(f"✅ Stake Increased! Tx: {tx_hash_hex[:10]}...", "INFO")

    async def decrease_stake(self, amount_apdx: float):
        """Decrease stake"""
        amount_wei = self.w3.to_wei(amount_apdx, 'ether')
        self.log(f"Decreasing stake by {amount_apdx} APDX...", "WARN")
        
        try:
            receipt = await self._send_tx(self.main_contract.functions.decreaseStake(amount_wei))
            # [Fix]
            tx_hash_hex = receipt['transactionHash'].hex()
            self.log(f"✅ Stake Decreased! Tx: {tx_hash_hex[:10]}...", "INFO")
        except Exception as e:
            self.log(f"Decrease failed (Check min stake?): {str(e)}", "ERROR")

    async def exit_network(self):
        """Completely exit the network"""
        self.log("🚨 EXITING NETWORK & WITHDRAWING ALL STAKE...", "WARN")
        try:
            receipt = await self._send_tx(self.main_contract.functions.exitNetwork())
            # [Fix]
            tx_hash_hex = receipt['transactionHash'].hex()
            self.log(f"✅ Exited Network! Funds returned. Tx: {tx_hash_hex[:10]}...", "INFO")
            self.stop()
        except Exception as e:
            self.log(f"Exit failed: {str(e)}", "ERROR")

    # ================= Internal Logic =================

    async def _ensure_registration(self):
        validator_info = await asyncio.to_thread(
            self.main_contract.functions.validators(self.account.address).call
        )
        is_active = validator_info[2]
        
        if is_active:
            self.log("Validator already registered.", "INFO")
            return

        self.log("Validator not registered. initializing...", "WARN")
        stake_amount = self.w3.to_wei(100, 'ether')

        balance = await asyncio.to_thread(
            self.token.functions.balanceOf(self.account.address).call
        )
        if balance < stake_amount:
            self.log("Insufficient balance. Requesting faucet...", "WARN")
            await self._send_tx(self.token.functions.faucet())
            self.log("Faucet claimed.", "INFO")

        self.log("Approving token...", "INFO")
        try:
            await self._send_tx(self.token.functions.approve(self.contract_addr, stake_amount))
        except Exception:
            pass

        self.log("Registering validator...", "INFO")
        await self._send_tx(self.main_contract.functions.registerValidator(stake_amount))
        self.log("Registration successful!", "INFO")

    async def _event_loop(self):
        event_filter = self.main_contract.events.TaskCreated.create_filter(from_block='latest')
        while self.running:
            try:
                new_entries = await asyncio.to_thread(event_filter.get_new_entries)
                for event in new_entries:
                    task_id = event['args']['taskId']
                    ipfs_cid = event['args']['ipfsCID']
                    reward = self.w3.from_wei(event['args']['reward'], 'ether')
                    self.log(f"[NEW TASK] ID: {task_id} | Reward: {reward} APDX", "INFO")
                    asyncio.create_task(self._process_task(task_id, ipfs_cid))
                await asyncio.sleep(2)
            except Exception as e:
                self.log(f"Loop error: {str(e)}", "ERROR")
                await asyncio.sleep(5)

    async def _process_task(self, task_id, cid):
        try:
            file_path = await self._download_ipfs(task_id, cid)
            result_hash = await self._run_docker(file_path)
            
            salt = os.urandom(32)
            commitment = Web3.solidity_keccak(['bytes32', 'bytes32'], [result_hash, salt])
            
            self.log(f"Committing task {task_id}...", "INFO")
            await self._send_tx(self.main_contract.functions.commitResult(task_id, commitment))
            
            self.log(f"Waiting to reveal task {task_id}...", "INFO")
            await asyncio.sleep(5) 
            
            self.log(f"Revealing task {task_id}...", "INFO")
            await self._send_tx(self.main_contract.functions.revealResult(task_id, result_hash, salt))
            self.log(f"Task {task_id} Revealed!", "INFO")
            
            if self.greedy_mode:
                self.log(f"Greedy Mode: Scheduling finalize for Task {task_id}...", "INFO")
                asyncio.create_task(self._auto_finalize(task_id))
            else:
                self.log(f"Passive Mode: Task {task_id} complete.", "INFO")

        except Exception as e:
            self.log(f"Task {task_id} failed: {str(e)}", "ERROR")

    async def _auto_finalize(self, task_id):
        try:
            task = await asyncio.to_thread(self.main_contract.functions.tasks(task_id).call)
            deadline = task[3]
            
            while True:
                latest = await asyncio.to_thread(self.w3.eth.get_block, 'latest')
                now = latest['timestamp']
                target_time = deadline + 120
                wait_seconds = target_time - now
                
                if wait_seconds > 0:
                    if wait_seconds % 30 == 0:
                        self.log(f"Task {task_id}: Waiting {wait_seconds}s for finalize window...", "INFO")
                    await asyncio.sleep(5)
                else:
                    break
            
            self.log(f"⚡ Time reached! Finalizing Task {task_id}...", "WARN")
            receipt = await self._send_tx(self.main_contract.functions.finalizeTask(task_id))
            
            if receipt.status == 1:
                self.log(f"✅✅✅ SUCCESS: Task {task_id} Finalized! Rewards Claimed.", "INFO")
            else:
                self.log(f"❌ Finalize failed (Reverted)", "ERROR")

        except Exception as e:
            if "already finalized" in str(e):
                self.log(f"Task {task_id} already finalized.", "INFO")
            else:
                self.log(f"Auto-finalize error: {str(e)}", "ERROR")

    async def _download_ipfs(self, task_id, cid):
        filename = f"Task_{task_id}.lean"
        path_obj = Path(os.getcwd()) / filename
        
        if cid.startswith("QmSimulated"):
            self.log(f"Simulating download for {cid}", "WARN")
            dummy_code = "import Mathlib\ntheorem test : 1 + 1 = 2 := by norm_num"
            with open(path_obj, "w") as f:
                f.write(dummy_code)
            return str(path_obj)

        gateways = []
        if self.pinata_gateway:
            gateways.append(f"https://{self.pinata_gateway}/ipfs/{cid}")
        gateways.extend([
            f"https://cloudflare-ipfs.com/ipfs/{cid}",
            f"https://ipfs.io/ipfs/{cid}",
            f"https://gateway.pinata.cloud/ipfs/{cid}"
        ])

        async with httpx.AsyncClient() as client:
            for url in gateways:
                self.log(f"Downloading from {url}...", "INFO")
                try:
                    resp = await client.get(url, timeout=15.0)
                    if resp.status_code == 200:
                        with open(path_obj, "wb") as f:
                            f.write(resp.content)
                        self.log("Download success.", "INFO")
                        return str(path_obj)
                except Exception:
                    continue
        
        raise Exception("All IPFS gateways failed")

    async def _run_docker(self, file_path):
        self.log("Starting Docker verification...", "INFO")
        abs_path = os.path.abspath(file_path)
        
        cmd = [
            "docker", "run", "--rm", "--network", "none",
            "--cpus", "2", "--memory", "8g",
            "-v", f"{abs_path}:/data/Task.lean",
            self.docker_image
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await proc.communicate()
        output = stdout.decode()
        
        # [Core Fix] Check status first, if FAILURE, classify the error
        if "Status: FAILURE" in output:
            if "CHEAT DETECTED" in output or "ERROR_AXIOM_CHECK_FAILED" in output:
                 self.log("⚠️ Cheat Detected by Docker!", "WARN")
                 # Error code 1: Cheating
                 return Web3.keccak(text="ERROR_AXIOM_CHECK_FAILED")
            else:
                 self.log("⚠️ Compilation or Runtime Failed!", "WARN")
                 # [New] Error code 2: Compilation/Runtime error
                 # Regardless of the specific error log, return this unified hash
                 return Web3.keccak(text="COMPILATION_FAILED")

        # Only parse the specific hash when SUCCESS
        match = re.search(r"Deterministic Hash: ([a-f0-9A-Z_]+)", output)
        if match:
            hash_str = match.group(1)
            if not hash_str.startswith("0x") and len(hash_str) != 64:
                 return Web3.keccak(text=hash_str)
            return "0x" + hash_str
        else:
            self.log(f"Docker output parsing failed: {output[:100]}", "ERROR")
            # Unparsable results are also classified as compilation failure
            return Web3.keccak(text="COMPILATION_FAILED")

    async def _send_tx(self, func_call):
        nonce = await asyncio.to_thread(self.w3.eth.get_transaction_count, self.account.address, 'pending')
        tx = await asyncio.to_thread(func_call.build_transaction, {'from': self.account.address, 'nonce': nonce, 'gasPrice': self.w3.eth.gas_price, 'gas': 2000000})
        signed_tx = self.account.sign_transaction(tx)
        tx_hash = await asyncio.to_thread(self.w3.eth.send_raw_transaction, signed_tx.raw_transaction)
        receipt = await asyncio.to_thread(self.w3.eth.wait_for_transaction_receipt, tx_hash)
        if receipt.status != 1: raise Exception(f"Transaction failed: {tx_hash.hex()}")
        return receipt