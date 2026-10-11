"""Adapt local Windows tool paths to the SDK's POSIX path syntax."""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import TYPE_CHECKING

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest

from deepagents_code.offload import _filesystem_tool_path

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain_core.messages import ToolMessage
    from langgraph.types import Command

_PATH_ARGUMENTS = {
    "ls": "path",
    "glob": "path",
    "grep": "path",
    "read_file": "file_path",
    "write_file": "file_path",
    "edit_file": "file_path",
    "delete": "file_path",
}


class WindowsPathMiddleware(AgentMiddleware):
    """Normalize host and relative paths before filesystem tool validation.

    Install only for local Windows backends. Virtual absolute routes remain
    unchanged, and traversal validation remains owned by the SDK.
    """

    def __init__(self, cwd: str) -> None:
        """Initialize with the session's absolute Windows working directory.

        Args:
            cwd: Workspace used to anchor relative filesystem tool arguments.
        """
        self._cwd = PureWindowsPath(cwd)

    def _path(self, raw: str) -> str:
        path = PureWindowsPath(raw)
        if ".." in path.parts or raw.startswith("~"):
            return raw
        if path.is_absolute():
            return _filesystem_tool_path(path)
        if path.drive or path.root:
            return raw
        return _filesystem_tool_path(self._cwd / path)

    def _request(self, request: ToolCallRequest) -> ToolCallRequest:
        argument = _PATH_ARGUMENTS.get(request.tool_call["name"])
        if argument is None:
            return request
        args = dict(request.tool_call["args"])
        raw = args.get(argument)
        if raw is None and argument == "path":
            raw = "."
        if not isinstance(raw, str):
            return request
        args[argument] = self._path(raw)
        return request.override(tool_call={**request.tool_call, "args": args})

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[object]],
    ) -> ToolMessage | Command[object]:
        """Dispatch a filesystem call with a normalized local path.

        Returns:
            The tool result from the next handler.
        """
        return handler(self._request(request))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    ) -> ToolMessage | Command[object]:
        """Dispatch an asynchronous filesystem call with a normalized path.

        Returns:
            The tool result from the next handler.
        """
        return await handler(self._request(request))
