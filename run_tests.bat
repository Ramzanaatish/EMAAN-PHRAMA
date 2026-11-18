@echo off
REM Pharma Purchase Assistant — run the test suite (Windows).
REM Double-click this file, or run: run_tests.bat
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
    echo Virtual environment not found. Run the install steps in run_instruction.md first.
    pause
    exit /b 1
)
.venv\Scripts\python -m pytest tests\ -q
if errorlevel 1 (
    echo.
    echo TESTS FAILED — do not deploy. Send the output above.
) else (
    echo.
    echo ALL TESTS PASSED.
)
pause
