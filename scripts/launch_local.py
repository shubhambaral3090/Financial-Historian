"""Use the installed Python to prepare and start the local browser application."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


MINIMUM_PYTHON = (3, 12)
MAXIMUM_PYTHON = (4, 0)
TESTED_FALLBACK = "Python 3.14.6 or Python 3.12"


class SetupError(RuntimeError):
    """A setup failure that must stop before dependent commands run."""


def compatible_version(version):
    """New Python 3.x releases are eligible, subject to dependency wheels."""
    return MINIMUM_PYTHON <= tuple(version[:2]) < MAXIMUM_PYTHON


def launcher_paths(output):
    """Read installed paths from old and new Windows launchers' ``py -0p``.

    Only listing commands are used: asking ``py`` to run an absent version can
    invoke Python Install Manager's automatic installation behavior.
    """
    paths = []
    for line in output.splitlines():
        match = re.search(r'(?:[A-Za-z]:[\\/]|\\\\).+?\.exe\s*$', line)
        if match:
            path = match.group().strip()
            if path.lower().endswith(("\\python.exe", "/python.exe")) and path not in paths:
                paths.append(path)
    return paths


def select_interpreter(*, executable=sys.executable, version=sys.version_info,
                       windows=os.name == "nt", runner=subprocess.run,
                       which=shutil.which):
    """Prefer the current compatible Python; otherwise probe installed paths.

    Never installs a runtime, and never guesses a version-specific launcher
    invocation. The dependency wheel preflight is a separate necessary check.
    """
    if compatible_version(version):
        return executable
    candidates = []
    if windows:
        try:
            listed = runner(["py", "-0p"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, timeout=10)
            if listed.returncode == 0:
                candidates.extend(launcher_paths(listed.stdout))
        except (OSError, subprocess.TimeoutExpired):
            pass
    for name in ("python3", "python"):
        path = which(name)
        if path and path != executable and path not in candidates:
            candidates.append(path)
    available = []
    for candidate in candidates:
        try:
            probe = runner([candidate, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=10)
            if probe.returncode != 0:
                continue
            reported = tuple(int(part) for part in probe.stdout.strip().split("."))
            if len(reported) == 3 and compatible_version(reported):
                available.append((reported, candidate))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    if available:
        return max(available)[1]
    raise SetupError("No compatible installed Python was found. Python >=3.12 and <4 is required. "
                     f"Install {TESTED_FALLBACK}, then launch again. No Python version was installed automatically.")


def _run(command, root, runner, description):
    try:
        result = runner(command, cwd=str(root))
    except OSError as error:
        raise SetupError(f"{description}: {error}") from None
    if result.returncode:
        raise SetupError(f"{description}. The command exited with code {result.returncode}; review its output above.")


def prepare_environment(root: Path, *, executable=sys.executable,
                        windows=os.name == "nt", runner=subprocess.run) -> Path:
    """Verify each prerequisite before starting installation or the app.

    Existence checks protect against launcher wrappers that report success even
    when they failed to create an environment. Dependency installation starts
    only after all required wheels are available for the selected interpreter.
    """
    requirements = root / "requirements.txt"
    if not requirements.is_file() or not (root / "app.py").is_file():
        raise SetupError("Extract the complete ZIP before launching. app.py and requirements.txt must be beside the launcher.")
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if windows else "bin/python")
    marker = environment / "financial-historian-requirements.sha256"
    if not python.is_file():
        print("Creating the local Python environment with your installed Python...", flush=True)
        _run([executable, "-m", "venv", str(environment)], root, runner,
             "The Python environment could not be created. Check that this folder is writable")
        if not python.is_file():
            raise SetupError("Python did not create .venv's interpreter. Installation has stopped. Check the environment creation output above.")
    _run([str(python), "-c", "import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (4, 0) else 1)"],
         root, runner, "The local Python environment is unusable or outside Python >=3.12,<4. "
         "Rename .venv and launch again; your existing files have not been removed")
    expected = hashlib.sha256(requirements.read_bytes()).hexdigest()
    try:
        current = marker.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        current = ""
    imports = [str(python), "-c", "import streamlit, requests, openpyxl, lxml, yfinance"]
    if current == expected:
        try:
            probe = runner(imports, cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ready = probe.returncode == 0
        except OSError:
            ready = False
    else:
        ready = False
    if not ready:
        print("Checking compatible dependency wheels. First launch requires internet access...", flush=True)
        # Download the complete dependency set before changing the environment.
        # No compiler or source-distribution build is silently required, and a
        # future Python with missing wheels receives an actionable explanation.
        with tempfile.TemporaryDirectory(prefix="financial-historian-wheels-") as wheel_dir:
            _run([str(python), "-m", "pip", "download", "--only-binary=:all:",
                  "--dest", wheel_dir, "-r", str(requirements)], root, runner,
                 "Compatible dependency wheels could not be obtained. Check the network or package error above. "
                 f"If this Python release has no compatible builds yet, use {TESTED_FALLBACK}. "
                 "No packages or another Python version were installed")
            print("Installing compatible dependency wheels...", flush=True)
            _run([str(python), "-m", "pip", "install", "--no-index", "--only-binary=:all:",
                  "--find-links", wheel_dir, "-r", str(requirements)], root, runner,
                 "Dependency installation failed. Check the package error above")
        _run(imports, root, runner, "Installed dependencies could not be imported")
        _run([str(python), "-m", "pip", "check"], root, runner, "Dependency compatibility check failed")
        marker.write_text(expected, encoding="ascii")
    return python


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        executable = select_interpreter()
        print(f"Using compatible installed Python: {executable}", flush=True)
        python = prepare_environment(root, executable=executable)
        print("Opening Fishtorian. Keep this window open; press Ctrl+C to stop.", flush=True)
        command = [str(python), "-m", "streamlit", "run", str(root / "app.py"),
                   "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=false",
                   "--browser.gatherUsageStats=false"]
        _run(command, root, subprocess.run, "The app could not start. Another copy may be using port 8501")
        return 0
    except SetupError as error:
        print(f"\n{error}", flush=True)
        return 1
    except OSError as error:
        print(f"\nLocal setup could not finish: {error}", flush=True)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
