@echo off
pushd "%~dp0"
python "%~dp0compress.py" "%*"
set ec=%ERRORLEVEL%
popd

if %ec% neq 0 (
    echo ERROR: compress.py exited with code %ec%.
    pause
    exit /b %ec%
)

exit /b 0
