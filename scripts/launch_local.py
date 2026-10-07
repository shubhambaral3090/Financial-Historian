"""Use the installed Python to prepare and start the local browser application."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys


class SetupError(RuntimeError):
    """A setup failure that must stop before dependent commands run."""


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
    when they failed to create an environment. No absent Python version is probed.
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
    _run([str(python), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
         root, runner, "The local Python environment is unusable. Rename .venv and launch again")
    expected = hashlib.sha256(requirements.read_bytes()).hexdigest()
    try:
        current = marker.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        current = ""
    imports = [str(python), "-c", "import streamlit, requests, openpyxl, lxml"]
    if current == expected:
        try:
            probe = runner(imports, cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ready = probe.returncode == 0
        except OSError:
            ready = False
    else:
        ready = False
    if not ready:
        print("Installing dependencies securely. First launch requires internet access...", flush=True)
        _run([str(python), "-m", "pip", "install", "-r", str(requirements)], root, runner,
             "Dependency installation failed. Check the package error above and your network connection")
        _run(imports, root, runner, "Installed dependencies could not be imported")
        _run([str(python), "-m", "pip", "check"], root, runner, "Dependency compatibility check failed")
        marker.write_text(expected, encoding="ascii")
    return python


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required. Python 3.12 and 3.14.6 have been tested.")
        return 1
    root = Path(__file__).resolve().parents[1]
    print(f"Using installed Python {sys.version.split()[0]}", flush=True)
    try:
        python = prepare_environment(root)
        print("Opening Financial Historian. Keep this window open; press Ctrl+C to stop.", flush=True)
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
