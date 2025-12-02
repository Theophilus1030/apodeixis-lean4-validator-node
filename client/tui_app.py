import os
import subprocess
import json
from datetime import datetime
from dotenv import load_dotenv
from web3 import Web3

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Footer, Static, Button, Label, RichLog, Input
from textual import work
from rich.text import Text

from node_core import ValidatorNode

load_dotenv()

# ================= Configuration =================
LOGO_RAW = r"""
  █████  ██████  ██████   ██████  ███████ ██ ██   ██ ███████
 ██   ██ ██   ██ ██    ██ ██   ██ ██      ██  ██ ██  ██     
 ███████ ██████  ██    ██ ██   ██ █████   ██   ███   ███████
 ██   ██ ██      ██    ██ ██   ██ ██      ██  ██ ██       ██
 ██   ██ ██       ██████  ██████  ███████ ██ ██   ██ ███████
"""
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")
DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "apodeixis-validator:v0.12")
ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"}]')

class StatusItem(Static):
    def __init__(self, label: str, value: str = "Pending...", id: str = None):
        super().__init__(id=id)
        self.label = label
    def set_value(self, val): self.update(f"[bold cyan]{self.label}:[/] {val}")

class ApodeixisApp(App):
    CSS = """
    Screen { align: center middle; background: #111; }
    #main-layout { width: 95%; height: 95%; border: solid #ffa500; background: #1e1e1e; padding: 1 2; }
    
    #logo { width: 100%; text-align: center; color: #ffa500; margin-bottom: 1; }
    
    /* Status panel */
    #status-grid { layout: grid; grid-size: 2; grid-gutter: 1 4; height: auto; border: dashed #444; padding: 1 2; background: #252525; }
    
    /* Control row - Row 1 (Node control) */
    #controls-row1 { height: 3; margin: 1 0; align: center middle; }
    .btn-ctrl { margin: 0 1; min-width: 16; }
    
    #btn-start { background: #006400; color: white; }
    #btn-stop { background: #8b0000; color: white; display: none; }
    #btn-mode { background: #555; color: white; }
    #btn-mode.greedy { background: #d4af37; color: black; }

    /* Control row - Row 2 (Fund management) */
    #controls-row2 { height: 3; margin-bottom: 1; align: center middle; }
    #input-amount { width: 16; margin-right: 1; background: #333; border: none; color: white; text-align: center; }
    #btn-stake-inc { background: #005577; min-width: 12; }
    #btn-stake-dec { background: #775500; min-width: 12; }
    #btn-exit { background: #440000; min-width: 12; color: #ffaaaa; }
    #btn-exit:hover { background: #ff0000; color: white; }

    /* Logs */
    #log-label { background: #333; color: white; text-style: bold; padding: 0 1; width: 100%; }
    #log-window { height: 1fr; border: solid #444; background: #000; color: #ccc; overflow-y: scroll; scrollbar-color: #ffa500; }
    """

    BINDINGS = [("q", "quit", "Quit"), ("r", "check_status", "Refresh")]

    is_node_running = False
    node_engine = None
    is_greedy = False 

    def compose(self) -> ComposeResult:
        yield Container(
            Vertical(
                Static(Text(LOGO_RAW, style="bold orange", no_wrap=True), id="logo"),
                Container(
                    StatusItem("RPC", id="status_rpc"),
                    StatusItem("Wallet", id="status_addr"),
                    StatusItem("Balance", id="status_bal"),
                    StatusItem("Docker", id="status_docker"),
                    id="status-grid"
                ),
                id="top-section"
            ),
            
            # Row 1: Node control
            Horizontal(
                Button("Start Node", id="btn-start", classes="btn-ctrl"),
                Button("Stop Node", id="btn-stop", classes="btn-ctrl"),
                Button("Mode: Passive", id="btn-mode", classes="btn-ctrl"),
                Button("Refresh (r)", id="btn-refresh", classes="btn-ctrl"),
                id="controls-row1"
            ),

            # Row 2: Fund management
            Horizontal(
                Input(placeholder="Amount", value="50", id="input-amount"),
                Button("+ Stake", id="btn-stake-inc", classes="btn-ctrl"),
                Button("- Stake", id="btn-stake-dec", classes="btn-ctrl"),
                Button("EXIT NET", id="btn-exit", classes="btn-ctrl"),
                id="controls-row2"
            ),

            Label(" LIVE LOGS ", id="log-label"),
            RichLog(id="log-window", highlight=True, markup=True, wrap=True),
            id="main-layout"
        )
        yield Footer()

    def on_mount(self):
        self.action_check_status()
        self.log_message("System ready. Configure stake and start.", "INFO")

    def log_message(self, msg, level="INFO"):
        log = self.query_one("#log-window", RichLog)
        color = {"INFO": "green", "WARN": "yellow", "ERROR": "red"}.get(level, "white")
        t = datetime.now().strftime("%H:%M:%S")
        log.write(f"[{t}] [{color}]{level}[/]: {msg}")
        self.call_later(log.scroll_end, animate=False)

    def on_button_pressed(self, event: Button.Pressed):
        bid = event.button.id
        if bid == "btn-refresh": self.action_check_status()
        elif bid == "btn-start": self.action_toggle_node(True)
        elif bid == "btn-stop": self.action_toggle_node(False)
        elif bid == "btn-mode": self.action_toggle_mode()
        
        # Fund operations
        elif bid in ["btn-stake-inc", "btn-stake-dec", "btn-exit"]:
            self.handle_fund_action(bid)

    @work(exclusive=True)
    async def handle_fund_action(self, btn_id):
        """Handle fund-related operations"""
        # 1. Initialize temporary node (if main node is not running)
        # Note: If node is running, reusing self.node_engine is better, but for simplicity, we always create a new temporary one
        # (web3.py supports concurrency, not a big issue)
        
        def log_bridge(m, l): self.call_later(self.log_message, m, l)
        
        # Reuse running node, or create new one
        node = self.node_engine if (self.is_node_running and self.node_engine) else ValidatorNode(log_bridge)
        
        amount_str = self.query_one("#input-amount", Input).value
        try:
            amount = float(amount_str)
        except ValueError:
            self.log_message("Invalid Amount!", "ERROR")
            return

        try:
            if btn_id == "btn-stake-inc":
                await node.increase_stake(amount)
            elif btn_id == "btn-stake-dec":
                await node.decrease_stake(amount)
            elif btn_id == "btn-exit":
                await node.exit_network()
                # After exiting network, automatically stop local node loop
                if self.is_node_running:
                    self.call_later(self.action_toggle_node, start=False)
            
            # Refresh balance display after operation completes
            self.action_check_status()
            
        except Exception as e:
            self.log_message(f"Action Failed: {e}", "ERROR")

    def action_toggle_mode(self):
        self.is_greedy = not self.is_greedy
        btn = self.query_one("#btn-mode", Button)
        if self.is_greedy:
            btn.label = "Mode: 🔥 GREEDY"
            btn.add_class("greedy")
            self.log_message("Switched to GREEDY mode", "WARN")
        else:
            btn.label = "Mode: 💤 PASSIVE"
            btn.remove_class("greedy")
            self.log_message("Switched to PASSIVE mode", "INFO")
        if self.node_engine: self.node_engine.greedy_mode = self.is_greedy

    def action_toggle_node(self, start: bool = None):
        if start is None: start = not self.is_node_running
        btn_start = self.query_one("#btn-start")
        btn_stop = self.query_one("#btn-stop")

        if start:
            self.is_node_running = True
            btn_start.display = False
            btn_stop.display = True
            self.run_node_loop()
        else:
            self.is_node_running = False
            btn_start.display = True
            btn_stop.display = False
            if self.node_engine: self.node_engine.stop()

    @work(exclusive=True)
    async def run_node_loop(self):
        def log_bridge(msg, level): self.call_later(self.log_message, msg, level)
        if not self.node_engine:
            try:
                self.node_engine = ValidatorNode(log_bridge, greedy=self.is_greedy)
            except Exception as e:
                self.call_later(self.log_message, f"Init Error: {e}", "ERROR")
                self.call_later(self.action_toggle_node, start=False)
                return
        
        self.node_engine.greedy_mode = self.is_greedy
        await self.node_engine.start()

    @work(exclusive=True)
    async def action_check_status(self):
        # ... (keep as is) ...
        rpc = self.query_one("#status_rpc", StatusItem)
        addr = self.query_one("#status_addr", StatusItem)
        bal = self.query_one("#status_bal", StatusItem)
        docker = self.query_one("#status_docker", StatusItem)

        rpc.set_value("[yellow]Connecting...[/]")
        try:
            w3 = Web3(Web3.HTTPProvider(RPC_URL))
            if w3.is_connected():
                cid = w3.eth.chain_id
                rpc.set_value(f"[green]Online (ID: {cid})[/]")
                if PRIVATE_KEY:
                    acct = w3.eth.account.from_key(PRIVATE_KEY)
                    short = f"{acct.address[:6]}...{acct.address[-4:]}"
                    addr.set_value(f"[green]{short}[/]")
                    if TOKEN_ADDRESS:
                        try:
                            ctr = w3.eth.contract(address=Web3.to_checksum_address(TOKEN_ADDRESS), abi=ERC20_ABI)
                            raw = ctr.functions.balanceOf(acct.address).call()
                            eth_val = w3.from_wei(raw, 'ether')
                            bal.set_value(f"[green]{eth_val} APDX[/]")
                        except Exception: bal.set_value("[red]Token Error[/]")
                    else: bal.set_value("[yellow]No Config[/]")
                else: addr.set_value("[yellow]No Key[/]")
            else: rpc.set_value("[red]Offline[/]")
        except Exception: rpc.set_value("[red]RPC Error[/]")

        docker.set_value("[yellow]Checking...[/]")
        try:
            subprocess.run(["docker", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            res = subprocess.run(["docker", "images", "-q", DOCKER_IMAGE], stdout=subprocess.PIPE, text=True)
            if res.stdout.strip(): docker.set_value(f"[green]Ready[/]")
            else: docker.set_value(f"[red]Missing Image[/]")
        except subprocess.CalledProcessError: docker.set_value("[bold red]Permission Denied[/]")
        except Exception: docker.set_value("[red]Error[/]")

if __name__ == "__main__":
    app = ApodeixisApp()
    app.run()