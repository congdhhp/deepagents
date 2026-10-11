# Windows single-file executable

The experimental Windows build contains dcode, a uv-managed CPython runtime,
and the package dependencies from `uv.lock`. The destination machine does not
need Python or uv to run the included providers, terminal UI, or local server.

The launcher keeps the extracted runtime alive until dcode exits. Both dcode
and its LangGraph server run with the included interpreter, so the server's
`python -m langgraph_cli` startup and dynamic imports retain their normal
behavior. Bundled Python is also added to the child process's PATH for coding
tasks that run `python`.

## Build

Build on Windows with uv installed. Run from `libs/code`:

```powershell
uv sync --group test
uv run --no-sync python scripts/build_windows_exe.py
```

The output is `dist/windows/onefile/dcode.exe`. Copy this file to another
Windows machine with the same architecture. The adjacent `dcode.build.json`
records the source commit, SHA-256 checksum, and binary size; it is optional
for running the executable.

For diagnosing packaging issues, build the directory version first:

```powershell
uv run --no-sync python scripts/build_windows_exe.py --format onedir
.\dist\windows\onedir\dcode\dcode.exe --version
```

That version requires the entire `dist/windows/onedir/dcode` directory.
`--python 3.13` selects the managed build/runtime interpreter (the default).

Build environments and staging directories stay under `build/windows-exe`.
The script uses `uv sync --frozen --no-editable --no-default-groups` for runtime
dependencies, rebuilds the four local packages from current source, and leaves
the development environment and lockfile unchanged. Its import path ignores
host Python installations and PYTHONPATH while allowing workspace imports.
It installs PyInstaller 6.22.3 in a separate builder environment; PyInstaller
is an actively maintained packaging tool with Windows support. Colorama 0.4.6
is included in the runtime because structlog's Windows console logging uses
this optional dependency. Neither tool is added to the project's runtime
dependency declarations by this build option.

## Run with LM Studio

Run from the project directory you want dcode to work on:

```powershell
$env:DEEPAGENTS_CODE_OPENAI_BASE_URL = "http://127.0.0.1:1234/v1"
$env:DEEPAGENTS_CODE_OPENAI_API_KEY = "lm-studio"
C:\Tools\dcode.exe --model "openai:openai/gpt-oss-20b"
```

Alternatively, use `--model "lmstudio:openai/gpt-oss-20b"` if that custom
provider is configured on the destination machine. The binary does not bundle
your profile, credentials, MCP settings, conversation history, or LLM weights.
It reads the user's normal dcode profile, or the profile selected by
`DEEPAGENTS_HOME`. `127.0.0.1` refers to the machine running the executable.

## Limits

- Single-file mode extracts the runtime into an OS temporary directory on each
  launch. Allow time and disk space for extraction; the runtime is removed on
  normal exit.
- Git, Node.js, external MCP servers, optional provider packages, and sandbox
  services are not included. Supply them separately when a task needs them.
- Automatic dcode updates are disabled by the launcher. Rebuild and replace
  the executable to update it; `dcode install`/`uninstall` and `dcode update`
  are not a persistent package-management workflow for this distribution.
- The executable is unsigned. Distribution signing and testing on a clean
  Windows machine are separate release steps.
- Existing provider and runtime errors are not changed by this packaging option.

Packaging behavior and platform restrictions follow the
[PyInstaller documentation](https://pyinstaller.org/en/stable/operating-mode.html).
