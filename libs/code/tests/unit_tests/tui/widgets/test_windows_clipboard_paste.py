"""Windows clipboard pastes use the same pipeline as terminal pastes."""

from types import SimpleNamespace
from unittest.mock import patch

import pyperclip
import pytest
from textual.app import App, ComposeResult

from deepagents_code.tui.widgets import _paste_textarea
from deepagents_code.tui.widgets.chat_input import ChatInput


class ClipboardApp(App[None]):
    """Record submissions to detect accidental sends of multiline pastes."""

    def __init__(self) -> None:
        super().__init__()
        self.submitted: list[str] = []

    def compose(self) -> ComposeResult:
        yield ChatInput()

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        self.submitted.append(event.value)


@pytest.mark.parametrize("key", ["ctrl+v", "ctrl+shift+v", "shift+insert"])
async def test_windows_paste_preserves_unicode_and_newlines(key: str) -> None:
    text = "Xin chào Việt Nam\nsecond line"
    app = ClipboardApp()
    with (
        patch.object(_paste_textarea, "sys", SimpleNamespace(platform="win32")),
        patch.object(pyperclip, "paste", return_value=text),
    ):
        async with app.run_test() as pilot:
            chat = app.query_one(ChatInput)
            chat.focus_input()
            await pilot.press(key)
            await pilot.pause()
            assert chat.value == text
            assert app.submitted == []


async def test_large_clipboard_paste_expands_when_submitted() -> None:
    text = "Xin chào\n" * 120
    app = ClipboardApp()
    with (
        patch.object(_paste_textarea, "sys", SimpleNamespace(platform="win32")),
        patch.object(pyperclip, "paste", return_value=text),
    ):
        async with app.run_test() as pilot:
            chat = app.query_one(ChatInput)
            chat.focus_input()
            await pilot.press("ctrl+v")
            await pilot.pause()
            assert chat.input_widget is not None
            assert chat.input_widget.text != text
            await pilot.press("enter")
            await pilot.pause()
            assert app.submitted == [text]


@pytest.mark.parametrize("payload", ["", pyperclip.PyperclipException("busy")])
async def test_unavailable_clipboard_preserves_draft(
    payload: str | pyperclip.PyperclipException,
) -> None:
    app = ClipboardApp()
    with (
        patch.object(_paste_textarea, "sys", SimpleNamespace(platform="win32")),
        patch.object(pyperclip, "paste") as paste,
    ):
        if isinstance(payload, Exception):
            paste.side_effect = payload
        else:
            paste.return_value = payload
        async with app.run_test() as pilot:
            chat = app.query_one(ChatInput)
            chat.set_value_at_end("existing draft")
            await pilot.press("ctrl+v")
            await pilot.pause()
            assert chat.value == "existing draft"
            assert app.submitted == []


async def test_other_platform_keeps_textual_clipboard() -> None:
    app = ClipboardApp()
    with patch.object(_paste_textarea, "sys", SimpleNamespace(platform="linux")):
        async with app.run_test() as pilot:
            app.copy_to_clipboard("local clipboard")
            chat = app.query_one(ChatInput)
            chat.focus_input()
            await pilot.press("ctrl+v")
            await pilot.pause()
            assert chat.value == "local clipboard"
