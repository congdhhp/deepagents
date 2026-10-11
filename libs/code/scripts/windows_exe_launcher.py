"""Keep the extracted Python runtime alive for the entire dcode session."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path


def runtime_directory() -> Path:
    """Locate the runtime included by the PyInstaller bundle.

    Returns:
        The extracted runtime directory.

    Raises:
        RuntimeError: If the launcher is not running from a bundle.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is None:
        msg = "This launcher must run from the packaged dcode executable."
        raise RuntimeError(msg)
    return Path(bundle) / "python"


def launch_environment(runtime: Path) -> dict[str, str]:
    """Expose bundled Python to the agent's shell without changing user settings.

    Returns:
        A child-process environment preserving provider and profile settings.
    """
    environment = os.environ.copy()
    environment["PATH"] = str(runtime) + os.pathsep + environment.get("PATH", "")
    # Updating an extracted runtime would be lost when the session ends.
    environment["DEEPAGENTS_CODE_AUTO_UPDATE"] = "0"
    environment["DEEPAGENTS_CODE_INVOKED_AS"] = Path(sys.executable).stem
    return environment


def wait_for_session(process: subprocess.Popen[bytes]) -> int:
    """Wait through console interrupts while dcode shuts down its server.

    Returns:
        The dcode child process exit code.
    """
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            # Windows delivers Ctrl+C to the child too. Keep the bundle alive
            # until dcode has stopped its server and released runtime files.
            continue


def main() -> int:
    """Run dcode with its bundled interpreter and inherit the caller's terminal.

    Returns:
        The CLI exit code, or 1 when the bundle is incomplete.
    """
    runtime = runtime_directory()
    interpreter = runtime / "python.exe"
    if not interpreter.is_file():
        print("dcode: the bundled Python runtime is missing.", file=sys.stderr)
        return 1
    # PyInstaller's DLL search path must not leak into the Python subprocess.
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    command = [str(interpreter), "-m", "deepagents_code", *sys.argv[1:]]
    with subprocess.Popen(command, env=launch_environment(runtime)) as process:
        return wait_for_session(process)


if __name__ == "__main__":
    raise SystemExit(main())
