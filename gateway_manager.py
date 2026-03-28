"""
IB Gateway manager using IBC + Xvfb (no Docker).

Prerequisites (one-time setup):
  1. Download IB Gateway stable offline installer from IBKR and install it:
       chmod +x ibgateway-stable-linux-x64.sh && ./ibgateway-stable-linux-x64.sh -q
     Default install path: ~/Jts/ibgateway/<version>/
  2. Download IBC zip from https://github.com/IbcAlpha/IBC/releases and unzip:
       unzip IBCLinux-*.zip -d ~/ibc && chmod +x ~/ibc/*.sh ~/ibc/scripts/*.sh
  3. sudo apt-get install -y xvfb

Set these env vars (or use a .env file):
  IBKR_USERNAME, IBKR_PASSWORD, IBC_PATH, GATEWAY_PATH
"""

import os
import signal
import socket
import subprocess
import tempfile
import time
import logging

logger = logging.getLogger(__name__)

PAPER_PORT = 4002
LIVE_PORT  = 4001


class GatewayManager:
    """Manages IB Gateway via IBC + Xvfb as subprocesses."""

    def __init__(
        self,
        username: str,
        password: str,
        trading_mode: str = "paper",     # "paper" | "live"
        ibc_path: str    = None,         # e.g. ~/ibc
        gateway_path: str = None,        # e.g. ~/Jts/ibgateway/10.29
        timezone: str    = "America/New_York",
        display: str     = ":99",
    ):
        self.username     = username
        self.password     = password
        self.trading_mode = trading_mode
        self.ibc_path     = os.path.expanduser(ibc_path or os.environ.get("IBC_PATH", "~/ibc"))
        self.gateway_path = os.path.expanduser(gateway_path or os.environ.get("GATEWAY_PATH", "~/Jts/ibgateway"))
        self.timezone     = timezone
        self.display      = display
        self.api_port     = PAPER_PORT if trading_mode == "paper" else LIVE_PORT

        self._xvfb_proc    = None
        self._gateway_proc = None
        self._config_file  = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _write_config(self) -> str:
        """Write a temporary IBC config.ini and return its path."""
        config = f"""
[IBController]
FIX=no
IbLoginId={self.username}
IbPassword={self.password}
TradingMode={self.trading_mode}
AcceptNonBrokerageAccountWarning=yes
AcceptIncomingConnectionAction=accept
AutoRestartTime=11:59 PM
ExistingSessionDetectedAction=primaryoverride
ReadOnlyApi=no
MinimizeMainWindow=yes
""".strip()
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", prefix="ibc_", delete=False
        )
        f.write(config)
        f.flush()
        self._config_file = f.name
        logger.debug(f"IBC config written to {self._config_file}")
        return self._config_file

    def _start_xvfb(self):
        """Start a virtual display with Xvfb."""
        if self._xvfb_proc and self._xvfb_proc.poll() is None:
            return  # Already running
        logger.info(f"Starting Xvfb on display {self.display}")
        self._xvfb_proc = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", "1024x768x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)  # Give Xvfb a moment to init

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start Xvfb + IB Gateway via IBC. Idempotent."""
        if self.is_running():
            logger.info("Gateway already running.")
            return

        self._start_xvfb()

        config_path  = self._write_config()
        gateway_path = self._gateway_path_resolved()
        script       = os.path.join(self.ibc_path, "gatewaystart.sh")

        env = os.environ.copy()
        env["DISPLAY"] = self.display

        logger.info(f"Starting IB Gateway via IBC: {script}")
        self._gateway_proc = subprocess.Popen(
            ["/bin/bash", script, config_path, gateway_path, self.ibc_path],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def stop(self):
        """Stop IB Gateway and Xvfb."""
        for proc, name in [(self._gateway_proc, "Gateway"), (self._xvfb_proc, "Xvfb")]:
            if proc and proc.poll() is None:
                logger.info(f"Stopping {name} (pid={proc.pid})")
                try:
                    proc.send_signal(signal.SIGTERM)
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._gateway_proc = None
        self._xvfb_proc    = None

        if self._config_file and os.path.exists(self._config_file):
            os.unlink(self._config_file)
            self._config_file = None

    def is_running(self) -> bool:
        return (
            self._gateway_proc is not None
            and self._gateway_proc.poll() is None
        )

    def wait_for_api(self, timeout: int = 90, poll: float = 2.0) -> bool:
        """Poll until the API port accepts TCP connections. Returns True when ready."""
        logger.info(f"Waiting for API on port {self.api_port} (up to {timeout}s)…")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.api_port), timeout=2):
                    logger.info("API port open — Gateway ready.")
                    return True
            except (ConnectionRefusedError, OSError):
                time.sleep(poll)
        logger.error("Timed out waiting for Gateway API.")
        return False

    def get_logs(self, lines: int = 60) -> str:
        """Return recent stdout from the gateway process."""
        if not self._gateway_proc or not self._gateway_proc.stdout:
            return "(gateway not running)"
        try:
            raw = self._gateway_proc.stdout.read1(8192)  # non-blocking read
            return raw.decode("utf-8", errors="replace")
        except Exception as e:
            return f"(log read error: {e})"

    def api_port_open(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self.api_port), timeout=1):
                return True
        except OSError:
            return False

    # ── Private ───────────────────────────────────────────────────────────────

    def _gateway_path_resolved(self) -> str:
        """
        If gateway_path points to a version directory (contains ibgateway binary),
        use it directly. Otherwise find the latest version subdirectory.
        """
        binary = os.path.join(self.gateway_path, "ibgateway")
        if os.path.isfile(binary):
            return self.gateway_path

        # Find latest version folder (e.g. ~/Jts/ibgateway/10.29)
        try:
            versions = sorted(
                d for d in os.listdir(self.gateway_path)
                if os.path.isdir(os.path.join(self.gateway_path, d))
            )
            if versions:
                return os.path.join(self.gateway_path, versions[-1])
        except FileNotFoundError:
            pass
        return self.gateway_path
