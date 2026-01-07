#!/bin/bash

# [Auto-Activate Venv]
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "[TEST] Running All Tests and Generating Report..."

# Create reports directory if not exists
mkdir -p reports

# [Auto-Install Dependency]
if ! pip freeze | grep -q "pytest-html"; then
    echo "[SETUP] Installing pytest-html..."
    pip install pytest-html
fi

# Check environment
echo "[DEBUG] Python: $(which python)"
echo "[DEBUG] Python Version: $(python --version)"

# Run pytest with HTML report generation
# --self-contained-html: Embed CSS/JS into a single HTML file
# [FIX] Use python -m pytest to ensure we use the venv's pytest with installed plugins
# [FIX] Removed --asyncio-mode=auto (requires pytest-asyncio which may not be installed)
python -m pytest tests/ --html=reports/test_report.html --self-contained-html -v

echo ""
echo "========================================================"
echo "[DONE] Test Report Generated: reports/test_report.html"
ls -l reports
echo "========================================================"
