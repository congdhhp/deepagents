"""Regression coverage for Windows paths returned by local filesystem tools."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from deepagents.backends import FilesystemBackend
from deepagents.backends.utils import validate_path
from langchain.agents.middleware.types import ToolCallRequest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage

from deepagents_code.windows_paths import WindowsPathMiddleware


def request_for(name: str, argument: str, path: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "args": {argument: path}, "id": "test"},
        tool=None,
        state={},
        runtime=Mock(spec=ToolRuntime),
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Uses the Windows host filesystem")
@pytest.mark.parametrize("relative", [False, True])
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_write_reaches_workspace(
    tmp_path: Path, *, relative: bool, asynchronous: bool
) -> None:
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    middleware = WindowsPathMiddleware(str(tmp_path))
    raw = "file.txt" if relative else str(tmp_path / "file.txt")
    request = request_for("write_file", "file_path", raw)

    def write(call: ToolCallRequest) -> ToolMessage:
        path = validate_path(call.tool_call["args"]["file_path"])
        result = backend.write(path, "content")
        assert result.error is None
        return ToolMessage(content="written", tool_call_id="test")

    async def awrite(call: ToolCallRequest) -> ToolMessage:
        return await asyncio.to_thread(write, call)

    if asynchronous:
        await middleware.awrap_tool_call(request, awrite)
    else:
        middleware.wrap_tool_call(request, write)
    assert (tmp_path / "file.txt").read_text() == "content"


@pytest.mark.parametrize(
    "path", ["../secret.txt", "C:/project/../secret.txt", "~/.env"]
)
def test_traversal_still_rejected(path: str) -> None:
    middleware = WindowsPathMiddleware("C:/project")
    request = request_for("read_file", "file_path", path)

    def read(call: ToolCallRequest) -> ToolMessage:
        with pytest.raises(ValueError, match="traversal"):
            validate_path(call.tool_call["args"]["file_path"])
        return ToolMessage(content="rejected", tool_call_id="test")

    middleware.wrap_tool_call(request, read)


@pytest.mark.parametrize(
    "path", ["/conversation_history/thread.md", "//?/C:/project/a.py"]
)
def test_absolute_route_preserved(path: str) -> None:
    middleware = WindowsPathMiddleware("C:/project")
    request = request_for("read_file", "file_path", path)

    def read(call: ToolCallRequest) -> ToolMessage:
        assert call.tool_call["args"]["file_path"] == path
        return ToolMessage(content="read", tool_call_id="test")

    middleware.wrap_tool_call(request, read)


@pytest.mark.skipif(sys.platform != "win32", reason="Uses the Windows host filesystem")
def test_glob_result_can_be_read(tmp_path: Path) -> None:
    (tmp_path / "cart.py").write_text("content")
    backend = FilesystemBackend(root_dir=tmp_path, virtual_mode=False)
    result = backend.glob("*.py", str(tmp_path))
    assert result.matches
    request = request_for("read_file", "file_path", result.matches[0]["path"])

    def read(call: ToolCallRequest) -> ToolMessage:
        result = backend.read(validate_path(call.tool_call["args"]["file_path"]))
        assert result.error is None
        assert result.file_data
        assert "content" in str(result.file_data)
        return ToolMessage(content="read", tool_call_id="test")

    WindowsPathMiddleware(str(tmp_path)).wrap_tool_call(request, read)
