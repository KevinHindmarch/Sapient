"""Entry point used by the desktop shell (and the frozen sapient-api.exe).

    sapient-api --data-dir DIR [--port 0] [--allowed-origin app://sapient]
    sapient-api --worker --data-dir DIR     (the read-only TWS connector)
    sapient-api --halt --data-dir DIR       (Emergency stop without the API; used by the
                                             tray when the API is not answering)

Protocol with the parent process (Electron main):
- The parent writes the per-launch API token as the first line on stdin.
  Tokens are never passed on the command line or written to disk.
- When the API is ready this prints one JSON line to stdout:
  {"event": "ready", "port": N}. Failures print {"event": "error", ...}.
- When stdin closes (the parent exited or crashed) this process exits, so a
  stale API can never outlive the app.
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def watch_parent(stdin) -> None:
    """Exit when the parent closes our stdin."""
    if sys.platform == "win32":
        # A thread blocked in ReadFile on the stdin pipe makes every later
        # CreateProcess hang on Windows (handle duplication waits for the
        # pending read; Python's platform module spawns `ver` at startup).
        # Poll with PeekNamedPipe instead, which never leaves a read pending.
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        peek = kernel32.PeekNamedPipe
        peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD,
                         wintypes.LPDWORD, wintypes.LPDWORD]
        peek.restype = wintypes.BOOL
        handle = msvcrt.get_osfhandle(stdin.fileno())
        error_broken_pipe = 109

        def run():
            available = wintypes.DWORD()
            while True:
                if not peek(handle, None, 0, None, ctypes.byref(available), None):
                    if ctypes.get_last_error() == error_broken_pipe:
                        os._exit(0)
                    return  # not a pipe (e.g. started from a console): nothing to watch
                time.sleep(0.5)
    else:
        def run():
            try:
                while stdin.readline():
                    pass
            finally:
                os._exit(0)
    threading.Thread(target=run, name="parent-watch", daemon=True).start()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sapient-api")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--allowed-origin", action="append", default=[])
    parser.add_argument("--worker", action="store_true", help="run the TWS connector instead of the API")
    parser.add_argument("--profile", choices=("paper", "live"), default="paper",
                        help="which TWS login the connector serves (live = real money)")
    parser.add_argument("--halt", action="store_true",
                        help="Emergency stop straight in the database, then exit (no token needed)")
    args = parser.parse_args(argv)

    if args.halt:
        return run_halt(args.data_dir)

    token = sys.stdin.readline().strip()
    if len(token) < 32:
        emit("error", code="token_missing", message="Expected the API token on stdin")
        return 2
    os.environ["SAPIENT_API_TOKEN"] = token
    os.environ["SAPIENT_DATA_DIR"] = str(args.data_dir)
    os.environ["SAPIENT_ALLOWED_ORIGINS"] = ",".join(args.allowed_origin)
    os.environ["SAPIENT_SKIP_MIGRATIONS"] = "1"  # done here so errors are reportable
    watch_parent(sys.stdin)

    try:
        from core.database import UserService
        from core.migrations import migrate
        migrate()
        UserService.ensure_local_user()
    except Exception as exc:  # e.g. a database from a newer Sapient
        emit("error", code="database", message=str(exc))
        return 3

    if args.worker:
        return run_worker(args.data_dir, args.profile)

    import uvicorn
    from backend.main import app

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))

    def announce():
        while not server.started:
            if server.should_exit:
                return
            time.sleep(0.05)
        emit("ready", port=port)
        # Market-hours checks (and the automatic orders they may queue) run inside the API
        # process, so they stop whenever the API - and with it the Emergency stop - is down.
        from core.strategy.scheduler import run_forever
        threading.Thread(target=run_forever, args=(lambda: server.should_exit,), name="scheduler",
                         daemon=True).start()
        threading.Thread(target=maintenance, args=(lambda: server.should_exit,), name="maintenance",
                         daemon=True).start()
    threading.Thread(target=announce, name="announce", daemon=True).start()

    server.run(sockets=[sock])
    return 0


def maintenance(should_stop, interval: float = 3600.0) -> None:
    """Daily database backup (with an integrity check) and market-cache clean-up, hourly checks."""
    import logging
    from core import backups, yahoo
    log = logging.getLogger("sapient.maintenance")
    while not should_stop():
        try:
            backups.daily_backup()
            yahoo.prune()
        except Exception:
            log.exception("maintenance failed")
        for _ in range(int(interval)):
            if should_stop():
                return
            time.sleep(1)


def run_worker(data_dir: Path, profile: str = "paper") -> int:
    import logging
    from logging.handlers import RotatingFileHandler
    from core.tws.worker import TwsWorker

    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    name = "tws-connector.log" if profile == "paper" else "tws-connector-live.log"
    handler = RotatingFileHandler(logs / name, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    emit("ready")
    TwsWorker(profile=profile).run()
    return 0


def run_halt(data_dir: Path) -> int:
    """Emergency stop when the API is not answering: same effect as the in-app kill switch.

    Switches AI Trading off, halts paper and live order sending and marks
    Sapient's working orders for cancelling (the connectors send the cancels).
    """
    os.environ["SAPIENT_DATA_DIR"] = str(data_dir)
    os.environ["SAPIENT_SKIP_MIGRATIONS"] = "1"
    try:
        from core.database import AITradingSettingsService, UserService
        user = UserService.get_local_user()
        if user is None:
            emit("halted", working_orders=0)
            return 0
        result = AITradingSettingsService.kill_switch(user["id"])
        emit("halted", working_orders=int((result or {}).get("paper_orders_cancel_requested") or 0))
        return 0
    except Exception as exc:
        emit("error", code="halt_failed", message=str(exc))
        return 4


if __name__ == "__main__":
    sys.exit(main())
