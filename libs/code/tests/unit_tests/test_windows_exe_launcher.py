"""Observable behavior of the standalone executable's runtime launcher."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.windows_exe_launcher import launch_environment, wait_for_session


def test_bundled_python_takes_precedence_without_changing_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime with spaces"
    runtime.mkdir()
    interpreter = runtime / ("python.exe" if sys.platform == "win32" else "python")
    interpreter.write_text("placeholder")
    interpreter.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "system"))
    monkeypatch.setenv("DEEPAGENTS_HOME", str(tmp_path / "profile"))
    monkeypatch.setenv("DEEPAGENTS_CODE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DEEPAGENTS_CODE_AUTO_UPDATE", "1")
    environment = launch_environment(runtime)
    located = shutil.which("python", path=environment["PATH"])
    assert located is not None
    assert Path(located) == interpreter
    assert environment["DEEPAGENTS_HOME"] == str(tmp_path / "profile")
    assert environment["DEEPAGENTS_CODE_OPENAI_API_KEY"] == "test-key"
    assert environment["DEEPAGENTS_CODE_AUTO_UPDATE"] == "0"
    assert os.environ["DEEPAGENTS_CODE_AUTO_UPDATE"] == "1"
    assert os.environ["PATH"] == str(tmp_path / "system")


@pytest.mark.parametrize("exit_code", [0, 7, 124])
def test_child_exit_status_is_preserved(exit_code: int) -> None:
    command = [sys.executable, "-c", f"raise SystemExit({exit_code})"]
    with subprocess.Popen(command) as process:
        assert wait_for_session(process) == exit_code
