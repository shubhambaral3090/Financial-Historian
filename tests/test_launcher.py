"""Regression tests for missing runtimes and incomplete Windows environments."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.launch_local import (
    SetupError, compatible_version, launcher_paths, prepare_environment,
    select_interpreter,
)


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "Folder with spaces"
    folder.mkdir()
    (folder / "requirements.txt").write_text("streamlit==1.55.0\n")
    (folder / "app.py").write_text("# application\n")
    return folder


def interpreter(root):
    python = root / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.touch()
    return python


def test_zero_exit_without_interpreter_stops_before_pip(root):
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)
    with pytest.raises(SetupError, match="did not create"):
        prepare_environment(root, windows=True, executable="installed-python", runner=runner)
    assert len(commands) == 1
    assert commands[0][:3] == ["installed-python", "-m", "venv"]
    assert not (root / ".venv" / "financial-historian-requirements.sha256").exists()


def test_creation_failure_stops_before_installation(root):
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1)
    with pytest.raises(SetupError, match="could not be created"):
        prepare_environment(root, windows=True, runner=runner)
    assert len(commands) == 1


def test_new_environment_uses_selected_python_and_is_reusable(root):
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        assert kwargs['cwd'] == str(root)
        if command[1:3] == ["-m", "venv"]:
            interpreter(root)
        return SimpleNamespace(returncode=0)
    python = prepare_environment(root, windows=True, executable="installed-3.14.6", runner=runner)
    assert python == root / ".venv" / "Scripts" / "python.exe"
    assert commands[0][0] == "installed-3.14.6"
    assert any(command[1:4] == ["-m", "pip", "install"] for command in commands)
    assert any(command[1:] == ["-m", "pip", "check"] for command in commands)
    downloads = [command for command in commands if command[1:4] == ["-m", "pip", "download"]]
    installs = [command for command in commands if command[1:4] == ["-m", "pip", "install"]]
    assert len(downloads) == len(installs) == 1
    assert "--only-binary=:all:" in downloads[0]
    assert "--only-binary=:all:" in installs[0]
    assert "--no-index" in installs[0]
    assert downloads[0][downloads[0].index("--dest") + 1] == installs[0][installs[0].index("--find-links") + 1]
    assert any("yfinance" in command[-1] for command in commands)
    commands.clear()
    prepare_environment(root, windows=True, runner=runner)
    assert not any("pip" in command or "venv" in command for command in commands)


def test_unusable_existing_environment_stops_and_preserves_files(root):
    python = interpreter(root)
    sentinel = root / ".venv" / "user-file.txt"
    sentinel.write_text("preserve")
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1)
    with pytest.raises(SetupError, match="unusable"):
        prepare_environment(root, windows=True, runner=runner)
    assert python.exists() and sentinel.read_text() == "preserve"
    assert len(commands) == 1


@pytest.mark.parametrize('failure', ['wheels', 'pip', 'imports', 'check'])
def test_install_failure_never_marks_environment_ready(root, failure):
    interpreter(root)
    def runner(command, **kwargs):
        failing = ((failure == 'wheels' and command[1:4] == ['-m', 'pip', 'download'])
                   or (failure == 'pip' and command[1:4] == ['-m', 'pip', 'install'])
                   or (failure == 'imports' and 'import streamlit' in command[-1])
                   or (failure == 'check' and command[1:] == ['-m', 'pip', 'check']))
        return SimpleNamespace(returncode=1 if failing else 0)
    with pytest.raises(SetupError):
        prepare_environment(root, windows=True, runner=runner)
    assert not (root / '.venv' / 'financial-historian-requirements.sha256').exists()


def test_changed_requirements_reinstall_and_update_marker(root):
    interpreter(root)
    marker = root / '.venv' / 'financial-historian-requirements.sha256'
    marker.write_text('old requirements')
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)
    prepare_environment(root, windows=True, runner=runner)
    assert any(command[1:4] == ['-m', 'pip', 'install'] for command in commands)
    assert marker.read_text() == hashlib.sha256((root / 'requirements.txt').read_bytes()).hexdigest()


def test_incomplete_zip_stops_without_commands(tmp_path):
    def runner(*args, **kwargs):
        pytest.fail('Should refuse incomplete extraction before running commands')
    with pytest.raises(SetupError, match='complete ZIP'):
        prepare_environment(tmp_path, runner=runner)


@pytest.mark.parametrize("version,expected", [
    ((3, 11, 14), False), ((3, 12, 0), True), ((3, 13, 5), True),
    ((3, 14, 6), True), ((3, 15, 0), True), ((3, 99, 1), True),
    ((4, 0, 0), False), ((2, 7, 18), False),
])
def test_python_range_includes_future_3x_not_python4(version, expected):
    assert compatible_version(version) is expected


def test_compatible_current_interpreter_needs_no_other_probe():
    def runner(*args, **kwargs):
        pytest.fail("A compatible current Python does not need launcher probes")
    assert select_interpreter(executable="current3.15", version=(3, 15, 0),
                              windows=True, runner=runner) == "current3.15"


def test_launcher_paths_preserve_spaces_and_deduplicate():
    text = "\n".join([
        "Installed Pythons found by py Launcher for Windows",
        r" -V:3.14 * C:\Program Files\Python314\python.exe",
        r" -3.12-64   C:\Python312\python.exe",
        r" -V:3.14   C:\Program Files\Python314\python.exe",
        r" -V:3.14   C:\Python314\pythonw.exe",
    ])
    assert launcher_paths(text) == [r"C:\Program Files\Python314\python.exe", r"C:\Python312\python.exe"]


def test_older_default_chooses_latest_compatible_installed_python():
    versions = {
        r"C:\Python311\python.exe": "3.11.12",
        r"C:\Python312\python.exe": "3.12.14",
        r"C:\Python314\python.exe": "3.14.6",
        r"C:\Python400\python.exe": "4.0.0",
    }
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        if command == ["py", "-0p"]:
            return SimpleNamespace(returncode=0, stdout="\n".join(" -V:version " + path for path in versions))
        assert command[1] == "-c"
        return SimpleNamespace(returncode=0, stdout=versions[command[0]])
    selected = select_interpreter(executable="old-python", version=(3, 11, 12),
                                  windows=True, runner=runner, which=lambda _: None)
    assert selected == r"C:\Python314\python.exe"
    assert commands[0] == ["py", "-0p"]
    assert all("install" not in command for command in commands)
    assert all(not command[0] == "py" or command == ["py", "-0p"] for command in commands)


def test_future_major_default_can_find_compatible_python_on_path():
    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="3.14.6")
    assert select_interpreter(executable="python4", version=(4, 0, 0), windows=False,
                              runner=runner, which=lambda _: "/installed/python3") == "/installed/python3"


def test_missing_or_broken_candidates_report_fallback_without_install():
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        if command == ["py", "-0p"]:
            raise OSError("no launcher")
        return SimpleNamespace(returncode=0, stdout="not a Python version")
    with pytest.raises(SetupError, match="No Python version was installed automatically"):
        select_interpreter(executable="old", version=(3, 11), windows=True,
                           runner=runner, which=lambda _: "invalid-python")
    assert not any("install" in command for command in commands)


def test_missing_wheels_stop_before_install_and_preserve_ready_marker(root):
    interpreter(root)
    marker = root / '.venv' / 'financial-historian-requirements.sha256'
    marker.write_text('previous successful setup')
    commands = []
    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=int(command[1:4] == ['-m', 'pip', 'download']))
    with pytest.raises(SetupError, match="Python 3.14.6 or Python 3.12"):
        prepare_environment(root, windows=True, runner=runner)
    assert not any(command[1:4] == ['-m', 'pip', 'install'] for command in commands)
    assert marker.read_text() == 'previous successful setup'


def test_windows_entrypoint_disables_automatic_runtime_installation():
    launcher = (Path(__file__).resolve().parents[1] / 'launch_windows.cmd').read_text()
    assert 'set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"' in launcher
    assert 'set "PYLAUNCHER_ALLOW_INSTALL="' in launcher
    assert 'call py -3 ' in launcher
    assert 'goto incomplete_zip' in launcher
