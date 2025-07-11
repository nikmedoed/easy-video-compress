@echo off
pushd "%~dp0"

if "%~1"=="" goto :launch_gui
if /I "%~1"=="gui" (
    shift
    goto :launch_gui
)
if /I "%~1"=="--gui" (
    shift
    goto :launch_gui
)

rem Build quoted arguments for CLI
set "QARGS="
:collect_cli
if "%~1"=="" goto :run_cli
set QARGS=%QARGS% "%~1"
shift
goto collect_cli

:run_cli
python "%~dp0compress.py" %QARGS%
set ec=%ERRORLEVEL%
popd
if %ec% neq 0 (
    echo ERROR: compress.py exited with code %ec%.
    pause
    exit /b %ec%
)
exit /b 0

:launch_gui
set "QARGS="
:collect_gui
if "%~1"=="" goto :run_gui
set QARGS=%QARGS% "%~1"
shift
goto collect_gui

:run_gui
set "PY_CMD=pythonw"
where pyw >nul 2>&1 && set "PY_CMD=pyw"
start "" %PY_CMD% "%~dp0compress.py" %QARGS%
popd
exit /b 0
