@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Financial Historian
echo Financial Historian - local Windows edition
echo.

if exist ".venv\Scripts\python.exe" goto check_environment

echo First launch: creating a private Python environment in this folder.
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
if not errorlevel 1 (
    py -3.12 -m venv .venv
    if errorlevel 1 goto environment_failed
    goto install_dependencies
)
py -3 -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
    if errorlevel 1 goto environment_failed
    goto install_dependencies
)

:try_python
where python >nul 2>nul
if errorlevel 1 goto python_missing
python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
if errorlevel 1 goto python_missing
python -m venv .venv
if errorlevel 1 goto environment_failed

:install_dependencies
echo.
echo Installing pinned dependencies. Internet access is needed on this first launch.
echo Standard secure PyPI connections and package verification are kept enabled.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -c "from pathlib import Path; import hashlib; Path('.venv/financial-historian-requirements.sha256').write_text(hashlib.sha256(Path('requirements.txt').read_bytes()).hexdigest(), encoding='ascii')"
if errorlevel 1 goto install_failed
goto run_app

:check_environment
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>nul
if errorlevel 1 goto environment_failed
".venv\Scripts\python.exe" -c "from pathlib import Path; import hashlib; marker=Path('.venv/financial-historian-requirements.sha256'); assert marker.exists() and marker.read_text(encoding='ascii') == hashlib.sha256(Path('requirements.txt').read_bytes()).hexdigest(); import streamlit, requests, openpyxl, lxml" >nul 2>nul
if errorlevel 1 goto install_dependencies

:run_app
echo.
echo Opening Financial Historian in your browser.
echo Keep this window open while using the app. Press Ctrl+C to stop it.
echo If the browser does not open, type 127.0.0.1:8501 in your browser.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=false --browser.gatherUsageStats=false
if errorlevel 1 goto startup_failed
exit /b 0

:python_missing
echo.
echo Python 3.11 or newer is required; Python 3.12 is recommended.
echo Install Python from https://www.python.org/downloads/windows/
echo Select the Python launcher or Add Python to PATH during installation.
echo Then double-click this launcher again.
pause
exit /b 1

:environment_failed
echo.
echo The local Python environment could not be created or is not usable.
echo Check that Python 3.11 or newer is installed and this folder is writable.
echo If .venv is from a different computer, rename it and launch again.
pause
exit /b 1

:install_failed
echo.
echo Dependency installation failed. Review the message above.
echo Check your internet connection and retry this launcher.
echo Do not bypass certificate verification to resolve a connection problem.
pause
exit /b 1

:startup_failed
echo.
echo The application could not start. Review the message above.
echo Another copy may already be using port 8501.
pause
exit /b 1
