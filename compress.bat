@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "SCRIPT_PATH=%SCRIPT_DIR%compress.py"
set "ec=0"

pushd "%SCRIPT_DIR%" >nul

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%SCRIPT_PATH%" %*
    set "ec=%ERRORLEVEL%"
    goto done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%SCRIPT_PATH%" %*
    set "ec=%ERRORLEVEL%"
    goto done
)

python "%SCRIPT_PATH%" %*
set "ec=%ERRORLEVEL%"

:done
popd >nul

if %ec% neq 0 (
    echo ERROR: compress.py exited with code %ec%.
    pause
)

exit /b %ec%
