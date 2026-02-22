@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: node_launcher.bat — GitHub-ready portable launcher
:: Auto-detect CAPSULE_ROOT from %~dp0 (two levels up)
:: Structure: CAPSULE_ROOT\devops\nodeupdate\node_launcher.bat
:: ============================================================

:: 1. Auto-detect CAPSULE_ROOT
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%A in ("%SCRIPT_DIR%\..") do set "DEVOPS_DIR=%%~fA"
for %%A in ("%DEVOPS_DIR%\..") do set "CAPSULE_ROOT=%%~fA"
echo [INFO] Capsule: %CAPSULE_ROOT%

:: 2. Locate Python
set "PYTHON_EXE="
for /d %%D in ("%CAPSULE_ROOT%\apps\python\current\python-*.amd64") do (
    if exist "%%D\python.exe" set "PYTHON_EXE=%%D\python.exe"
)
if not defined PYTHON_EXE (
    if exist "%CAPSULE_ROOT%\apps\python\current\python\python.exe" (
        set "PYTHON_EXE=%CAPSULE_ROOT%\apps\python\current\python\python.exe"
    )
)
if not defined PYTHON_EXE (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    echo [ERROR] Python not found. Install via Win+R -^> python
    pause
    exit /b 1
)

:: 3. Locate manager script
set "MANAGER=%SCRIPT_DIR%\node_manager.py"
if not exist "%MANAGER%" (
    echo [ERROR] node_manager.py not found: %MANAGER%
    pause
    exit /b 1
)

:: 4. UAC elevation check
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Requesting administrator privileges...
    powershell -NoProfile -Command ^
        "Start-Process cmd -Verb RunAs -ArgumentList '/c cd /d ""%SCRIPT_DIR%"" && ""%PYTHON_EXE%"" ""%MANAGER%"" %*'"
    exit /b 0
)

:: 5. Run manager
echo [INFO] NODE.JS PORTABLE MANAGER (Admin Mode)
"%PYTHON_EXE%" "%MANAGER%" %*
if %errorlevel% neq 0 (
    echo [ERROR] Manager exited with error code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo [OK] Completed successfully.
endlocal
exit /b 0
