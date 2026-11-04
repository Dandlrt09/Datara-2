# Building the Datara desktop application

Datara ships as a desktop application: one executable that opens its own window,
runs the API on a loopback port inside the same process and needs no Python
installed on the machine. This document is the build and acceptance recipe.

PyInstaller does not cross-compile: the bundle carries an interpreter for the
platform it was built on, so **the Windows executable is built on Windows**. The
frozen build can be produced and exercised on Linux or macOS in exactly the same
way, which is how the resource resolution and the sandbox worker mode are
verified during development.

## What "frozen" requires of the code

Three things break when an application is packaged, and each has one answer in
this repository:

| What breaks | Why | Where it is handled |
| --- | --- | --- |
| Paths relative to `__file__` | Inside a bundle `__file__` points into the unpacked archive, not into the checkout | `server/resources.py` — one resolver, `sys.frozen`/`sys._MEIPASS` |
| Uploads written next to the executable | An installed app usually cannot write beside itself | `server/resources.py` — frozen, uploads move to the data directory |
| Spawning `python script.py` | Frozen, `sys.executable` *is* the application | `server/desktop.py` — `--sandbox-runner` worker mode |

The read-only data files (`web/dist`, `server/migrations`) are declared in
`datara.spec`, which refuses to build if they are missing rather than producing
an application that boots to a blank window.

## Prerequisites

- **Python 3.12 or newer** on the build machine. 3.14 is supported from
  PyInstaller 6.21 onwards; the repository pins `pyinstaller>=6.21` for that
  reason.
- **Node.js** to build the frontend (it is not committed; `web/dist` is a build
  artifact).
- **WebView2 runtime** on the machine that *runs* the Windows build. It ships
  with Windows 10/11 by default; without it the window cannot be created.

## Build

```bash
# 1. Frontend: the spec refuses to build without a built SPA
cd web && npm ci && npm run build && cd ..

# 2. Python environment, including the desktop extras and the build tool
uv sync --all-extras

# 3. Freeze
uv run pyinstaller datara.spec --noconfirm
```

The result is the onedir layout in `dist/datara/` — the executable plus its
libraries beside it. Onedir is the default because it starts immediately;
`--onefile` unpacks the whole bundle on every launch and is only worth it when a
single file matters more than launch time.

To debug a frozen build, build it with a console instead of hunting for a log
file:

```bash
DATARA_BUILD_CONSOLE=1 uv run pyinstaller datara.spec --noconfirm
```

## Command-line modes

The same executable wears three hats. The second one exists so that a frozen
build can be exercised where there is no display at all:

| Invocation | Behaviour |
| --- | --- |
| `datara` | The application: API on a free loopback port, its own window, and the server dies with the window. |
| `datara --serve-only` | Serves with no window until interrupted. This is how the packaging is verified on a machine with no display, and what a hosted deployment would run. |
| `datara --sandbox-runner` | The sandbox child. Not meant to be typed by hand: the parent re-enters the executable with this flag to run the code the model wrote. |

## Where the application writes

| Path | Contents |
| --- | --- |
| `%USERPROFILE%\.datara\datara.db` (Windows) / `~/.datara/datara.db` | SQLite database |
| `~/.datara/.secret_key` | Fernet key for stored provider credentials. **Losing it loses the credentials, not the data.** |
| `~/.datara/uploads/` | Uploaded datasets (frozen builds only; from source they stay in the checkout) |
| `~/.datara/datara.log` | Application log — the only place to look in a windowed build, which has no console |

`DATARA_DB_PATH` moves all of it (the log and the uploads directory follow the
database), which is how a test run is isolated from a real install.

**Never place the data directory inside a synchronised folder** (OneDrive,
Dropbox, Google Drive). The privacy promise of the application — the raw file
never leaves the machine — is undone the moment an upload is synced to somebody
else's server.

## Acceptance test: nine points on a clean machine

Run this on a machine (or VM) that has **never had Python or this repository**:
install only the built `dist/datara/` folder and the WebView2 runtime. Record the
result of each point, plus the answers to point 9.

1. **Starts without a console and opens its own window.** No terminal flashes; a
   window appears on its own.
2. **Creates the data directory outside any synchronised folder.**
3. **Applies migrations into a brand-new database.** A fresh `datara.db` gets the
   schema; check `~/.datara/datara.log` if it does not.
4. **The frontend loads.** The window shows the application, not a blank page or
   a JSON document.
5. **Upload a CSV and profile it.** Columns, types and null counts appear.
6. **Execute code in the sandbox.** Ask a question whose answer requires
   computation; a table or a chart must come back. *This is the point the whole
   packaging exercise exists to protect: inside a frozen binary the sandbox child
   is the executable itself, spawned with `--sandbox-runner`.*
7. **A real question with the LLM returns a table plus a narrative.** Configure a
   provider and key first.
8. **Closing the window kills the process.** Check the task manager: no orphan
   `datara.exe` may survive. (On a graceful uvicorn shutdown hanging on the
   webview's keep-alive connections, the app forces the exit — an orphan here
   means that path broke.)
9. **Record the numbers:** size of `dist/datara/` on disk, and cold-start time
   from double-click to a usable window.

## Known limitations of this build

- **No file-write-size cap on Windows.** The Linux sandbox caps how large a file
  the generated code may write (`RLIMIT_FSIZE`). Windows has no per-process
  equivalent, so that one protection is absent; the Python-level `open` jail
  inside the sandbox runner still applies. The memory cap and the
  no-child-processes limit are enforced by a Job Object
  (`server/services/sandbox_win_job.py`), which is also what makes a sandbox
  child unable to outlive the application.
- **Unsigned binary.** Windows SmartScreen will warn on first run until the build
  is code-signed. Publishing with a published SHA-256 and the
  "More information → Run anyway" instruction is the honest interim path.
- **No updater.** Until there are users, updating means downloading the new
  build; the recommended shape is an in-app notice that reads GitHub Releases.
