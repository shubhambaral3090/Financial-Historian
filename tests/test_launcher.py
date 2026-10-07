"""Regression tests for missing runtimes and incomplete Windows environments."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.launch_local import SetupError, prepare_environment


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


@pytest.mark.parametrize('failure', ['pip', 'imports', 'check'])
def test_install_failure_never_marks_environment_ready(root, failure):
    interpreter(root)
    def runner(command, **kwargs):
        failing = ((failure == 'pip' and command[1:4] == ['-m', 'pip', 'install'])
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
