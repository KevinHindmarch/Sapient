"""Locate and load the official IBKR TWS API (``ibapi``) installed by the user.

Sapient does not ship IBKR's API: the user installs it from IBKR (licence
terms), normally into ``C:\\TWS API``. We add its ``source/pythonclient``
folder to ``sys.path`` at runtime. Never install ``ibapi`` from PyPI.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import sys

# Standard-library modules the official SDK imports. Importing them here makes
# PyInstaller bundle them, because the SDK itself is loaded from outside the
# frozen app at runtime.
import collections, decimal, enum, inspect, logging, math, queue, socket, struct, threading  # noqa: E401,F401


@dataclass(frozen=True)
class SdkInfo:
    folder: str          # folder that contains the ``ibapi`` package
    version: str | None


def candidate_folders(configured: str | None = None) -> list[Path]:
    folders = []
    if configured:
        folders.append(Path(configured))
    for root in (os.environ.get("SAPIENT_TWS_API_DIR"), r"C:\TWS API", r"C:\TWS_API",
                 os.path.join(os.environ.get("USERPROFILE", ""), "TWS API")):
        if root:
            folders.append(Path(root))
    expanded = []
    for folder in folders:
        expanded += [folder, folder / "source" / "pythonclient", folder / "pythonclient"]
    return expanded


def _read_version(package: Path) -> str | None:
    init = package / "__init__.py"
    try:
        for line in init.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("__version__"):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        return None
    return None


def find_sdk(configured: str | None = None) -> SdkInfo | None:
    for folder in candidate_folders(configured):
        package = folder / "ibapi"
        if (package / "client.py").is_file() and (package / "wrapper.py").is_file():
            return SdkInfo(folder=str(folder), version=_read_version(package))
    return None


class SdkUnavailable(RuntimeError):
    pass


def load_sdk(info: SdkInfo):
    """Import ibapi from the user's install; returns (EClient, EWrapper, Contract)."""
    if info.folder not in sys.path:
        sys.path.insert(0, info.folder)
    try:
        from ibapi.client import EClient
        from ibapi.contract import Contract
        from ibapi.wrapper import EWrapper
    except ImportError as exc:  # e.g. a newer SDK needing a module we lack
        raise SdkUnavailable(f"The IBKR API software could not be loaded ({exc.name or exc}).") from exc
    return EClient, EWrapper, Contract
