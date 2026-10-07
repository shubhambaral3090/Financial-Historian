@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Financial Historian
echo Financial Historian - local Windows edition
echo.

where py >nul 2>nul
if errorlevel 1 goto try_python
call py "%~dp0scripts\launch_local.py"
set "FH_EXIT_CODE=%ERRORLEVEL%"
goto finished

:try_python
where python >nul 2>nul
if errorlevel 1 goto python_missing
call python "%~dp0scripts\launch_local.py"
set "FH_EXIT_CODE=%ERRORLEVEL%"
goto finished

:python_missing
echo Python could not be found. Install Python 3.11 or newer.
echo Python 3.12 and 3.14.6 have been tested with this application.
echo Include the Python launcher or select Add Python to PATH when installing.
set "FH_EXIT_CODE=1"

:finished
if "%FH_EXIT_CODE%"=="0" exit /b 0
echo.
echo Startup did not finish. Read the specific error above.
pause
exit /b %FH_EXIT_CODE%
