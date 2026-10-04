#!/bin/bash
# ==================================================
# The Autonomous Alpha - Quick Start Script (Unix)
# ==================================================

set -e

echo ""
echo "========================================"
echo "   THE AUTONOMOUS ALPHA"
echo "   LLM-Centric Trading God"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found. Please install Python 3.10+"
    exit 1
fi

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "[INFO] Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "[INFO] Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check Ollama
echo ""
echo "[INFO] Checking Ollama..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[WARNING] Ollama not running. Please start Ollama first."
    echo "          Download from: https://ollama.com"
    echo ""
    echo "[INFO] After installing Ollama, run:"
    echo "       ollama pull deepseek-r1:32b-q4_K_M"
    echo "       ollama pull qwen2.5:32b-instruct-q4_K_M"
    echo ""
fi

# Parse arguments
MODE="health"
INTERVAL=5

while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        health|paper|live)
            MODE="$1"
            shift
            ;;
        test)
            echo "[INFO] Running tests..."
            python tests/test_integration.py
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Run the trading agent
echo ""
echo "[INFO] Starting trading agent in $MODE mode..."
echo "[INFO] Interval: $INTERVAL minutes"
echo ""

python -m src.main --mode "$MODE" --interval "$INTERVAL"
