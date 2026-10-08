@echo off
setlocal EnableExtensions
rem Never let either Python launcher install a runtime on our behalf.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "PYLAUNCHER_ALLOW_INSTALL="
cd /d "%~dp0"
title Financial Historian
echo Financial Historian - browser application
echo.

if not exist "%~dp0scripts\launch_local.py" goto incomplete_zip

where py >nul 2>nul
if errorlevel 1 goto try_python
call py -3 "%~dp0scripts\launch_local.py"
set "FH_EXIT_CODE=%ERRORLEVEL%"
goto finished

:try_python
where python >nul 2>nul
if errorlevel 1 goto python_missing
call python "%~dp0scripts\launch_local.py"
set "FH_EXIT_CODE=%ERRORLEVEL%"
goto finished

:python_missing
echo Python could not be found. Install Python 3.12 or newer, below Python 4.
echo Python 3.12 and 3.14.6 have been tested with this application.
echo Include the Python launcher or select Add Python to PATH when installing.
set "FH_EXIT_CODE=1"
goto finished

:incomplete_zip
echo Extract the complete ZIP to a folder before running this launcher.
echo scripts\launch_local.py is missing. Do not launch from inside the ZIP preview.
set "FH_EXIT_CODE=1"

:finished
if "%FH_EXIT_CODE%"=="0" exit /b 0
echo.
echo Startup did not finish. Read the specific error above.
pause
exit /b %FH_EXIT_CODE%
