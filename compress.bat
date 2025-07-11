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

python "%~dp0compress.py" %*
set ec=%ERRORLEVEL%
popd
if %ec% neq 0 (
    echo ERROR: compress.py exited with code %ec%.
    pause
    exit /b %ec%
)
exit /b 0

:launch_gui
set "PY_CMD=pythonw"
where pyw >nul 2>&1 && set "PY_CMD=pyw"
start "" "%PY_CMD%" "%~dp0compress.py" %*
popd
exit /b 0
