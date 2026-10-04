@echo off
REM ==================================================
REM The Autonomous Alpha - Quick Start Script (Windows)
REM ==================================================

echo.
echo ========================================
echo   THE AUTONOMOUS ALPHA
echo   LLM-Centric Trading God
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    exit /b 1
)

REM Check if venv exists
if not exist "venv" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install dependencies
echo [INFO] Installing dependencies...
pip install -q --upgrade pip
pip install -q -r requirements.txt

REM Check Ollama
echo.
echo [INFO] Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Ollama not running. Please start Ollama first.
    echo           Download from: https://ollama.com
    echo.
    echo [INFO] After installing Ollama, run:
    echo        ollama pull deepseek-r1:32b-q4_K_M
    echo        ollama pull qwen2.5:32b-instruct-q4_K_M
    echo.
)

REM Parse arguments
set MODE=health
set INTERVAL=5

:parse_args
if "%1"=="" goto end_parse
if "%1"=="--mode" (
    set MODE=%2
    shift
)
if "%1"=="--interval" (
    set INTERVAL=%2
    shift
)
if "%1"=="health" set MODE=health
if "%1"=="paper" set MODE=paper
if "%1"=="live" set MODE=live
if "%1"=="test" goto run_tests
shift
goto parse_args
:end_parse

REM Run tests if requested
:run_tests
if "%MODE%"=="test" (
    echo [INFO] Running tests...
    python tests\test_integration.py
    exit /b 0
)

REM Run the trading agent
echo.
echo [INFO] Starting trading agent in %MODE% mode...
echo [INFO] Interval: %INTERVAL% minutes
echo.

python -m src.main --mode %MODE% --interval %INTERVAL%

exit /b 0
