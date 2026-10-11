"""Build a Windows executable containing dcode and a managed Python runtime.

Usage from libs/code:
    uv run --no-sync python scripts/build_windows_exe.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PACKAGE = Path(__file__).resolve().parents[1]
BUILD = PACKAGE / "build" / "windows-exe"
PYINSTALLER_VERSION = "6.22.3"
COLORAMA_VERSION = "0.4.6"


def run(
    command: Sequence[str],
    *,
    environment: dict[str, str] | None = None,
    cwd: Path = PACKAGE,
) -> str:
    """Run a build command in the package and preserve full failure output.

    Returns:
        The command's standard output.

    Raises:
        subprocess.CalledProcessError: If a build step fails.
    """
    print("Building:", subprocess.list2cmdline(command), flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, end="", flush=True)
        raise
    if result.stdout:
        print(result.stdout, end="", flush=True)
    return result.stdout.strip()


def prepare_runtime(python: str) -> Path:
    """Install pinned wheels, rebuilding the local packages from current source.

    Returns:
        The runtime Python executable.
    """
    runtime = BUILD / "environment"
    environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(runtime)}
    command = [
        "uv",
        "sync",
        "--frozen",
        "--no-default-groups",
        "--no-editable",
        "--python",
        python,
        "--managed-python",
    ]
    for package in (
        "deepagents-code",
        "deepagents",
        "deepagents-acp",
        "langchain-quickjs",
    ):
        command.extend(["--reinstall-package", package])
    run(command, environment=environment)
    runtime_python = runtime / "Scripts" / "python.exe"
    # structlog's Windows console logging requires this optional dependency.
    install_package(runtime_python, f"colorama=={COLORAMA_VERSION}")
    return runtime_python


def install_package(interpreter: Path, requirement: str) -> None:
    """Install one explicit build requirement with uv."""
    run(["uv", "pip", "install", "--python", str(interpreter), requirement])


def prepare_builder(python: str) -> Path:
    """Prepare build tooling separately from the dcode runtime.

    Returns:
        The builder Python executable.
    """
    builder = BUILD / "builder"
    run(
        [
            "uv",
            "venv",
            "--allow-existing",
            "--python",
            python,
            "--managed-python",
            str(builder),
        ]
    )
    builder_python = builder / "Scripts" / "python.exe"
    install_package(builder_python, f"pyinstaller=={PYINSTALLER_VERSION}")
    return builder_python


def inspect_runtime(interpreter: Path) -> dict[str, str]:
    """Find the managed interpreter and installed packages without guessing paths.

    Returns:
        Interpreter root, site-packages location, and Python DLL basename.
    """
    probe = (
        "import json,sys,sysconfig; "
        "print(json.dumps({'base':sys.base_prefix, "
        "'packages':sysconfig.get_path('purelib'), "
        "'dll':'python'+str(sys.version_info.major)+str(sys.version_info.minor)}))"
    )
    return json.loads(run([str(interpreter), "-c", probe]))


def assemble_runtime(interpreter: Path, destination: Path) -> None:
    """Copy Python and wheel contents into an isolated relocatable runtime."""
    layout = inspect_runtime(interpreter)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    shutil.copytree(layout["base"], destination, ignore=ignore)
    shutil.copytree(
        layout["packages"],
        destination / "Lib" / "site-packages",
        dirs_exist_ok=True,
        ignore=ignore,
    )
    configure_paths(destination, layout["dll"])
    commit = run(["git", "rev-parse", "HEAD"])
    info = destination / "Lib" / "site-packages" / "deepagents_code" / "_build_info.py"
    info.write_text(f'BUILD_COMMIT = "{commit[:7]}"\n', encoding="utf-8")
    validate_runtime(destination)
    run([str(destination / "python.exe"), "-m", "deepagents_code", "--version"])


def configure_paths(runtime: Path, dll: str) -> None:
    """Isolate host installations while preserving imports of workspace modules."""
    (runtime / f"{dll}._pth").write_text(
        ".\nLib\nDLLs\nLib/site-packages\nimport site\n",
        encoding="utf-8",
    )
    # ._pth excludes the current directory, including for `python -c`. Restore
    # that normal Python behavior for coding tasks without using host packages.
    (runtime / "Lib" / "site-packages" / "deepagents_code_portable.pth").write_text(
        "import sys; sys.path.insert(0, '')\n",
        encoding="utf-8",
    )


def validate_runtime(runtime: Path) -> None:
    """Prove workspace imports work without using a host Python installation."""
    with tempfile.TemporaryDirectory(prefix="import-probe-", dir=BUILD) as folder:
        workspace = Path(folder)
        (workspace / "portable_probe.py").write_text("answer = 42\n", encoding="utf-8")
        environment = {
            **os.environ,
            "PYTHONHOME": str(workspace / "missing-python"),
            "PYTHONPATH": str(workspace / "missing-packages"),
        }
        code = (
            "import deepagents_code, langgraph_cli, langchain_openai, "
            "langchain_quickjs, portable_probe; assert portable_probe.answer == 42"
        )
        run(
            [str(runtime / "python.exe"), "-c", code],
            environment=environment,
            cwd=workspace,
        )


def bundle_runtime(builder: Path, runtime: Path, format_name: str) -> Path:
    """Package the launcher and runtime with PyInstaller's console bootloader.

    Returns:
        The generated executable path.
    """
    output = PACKAGE / "dist" / "windows" / format_name
    run(
        [
            str(builder),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            f"--{format_name}",
            "--console",
            "--noupx",
            "--name",
            "dcode",
            "--distpath",
            str(output),
            "--workpath",
            str(BUILD / "pyinstaller"),
            "--specpath",
            str(BUILD),
            "--add-data",
            f"{runtime}:python",
            str(PACKAGE / "scripts" / "windows_exe_launcher.py"),
        ]
    )
    return output / ("dcode.exe" if format_name == "onefile" else "dcode/dcode.exe")


def write_manifest(executable: Path, format_name: str) -> None:
    """Record the build provenance and checksum beside the executable."""
    with executable.open("rb") as binary:
        checksum = hashlib.file_digest(binary, "sha256").hexdigest()
    manifest = {
        "commit": run(["git", "rev-parse", "HEAD"]),
        "format": format_name,
        "platform": sys.platform,
        "pyinstaller": PYINSTALLER_VERSION,
        "sha256": checksum,
        "size_bytes": executable.stat().st_size,
        "lock_sha256": hashlib.sha256((PACKAGE / "uv.lock").read_bytes()).hexdigest(),
    }
    executable.with_suffix(".build.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Build and smoke-test the requested Windows executable.

    Raises:
        SystemExit: If invoked outside Windows.
    """
    if sys.platform != "win32":
        msg = "Build this executable on Windows."
        raise SystemExit(msg)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default="3.13", help="uv-managed Python version")
    parser.add_argument("--format", choices=("onefile", "onedir"), default="onefile")
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    interpreter = prepare_runtime(args.python)
    builder = prepare_builder(args.python)
    with tempfile.TemporaryDirectory(prefix="payload-", dir=BUILD) as staging:
        runtime = Path(staging) / "python"
        assemble_runtime(interpreter, runtime)
        executable = bundle_runtime(builder, runtime, args.format)
    run([str(executable), "--version"])
    write_manifest(executable, args.format)
    print(f"Built {executable} ({executable.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
