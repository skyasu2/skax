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

# Run pytest with HTML report generation
# --self-contained-html: Embed CSS/JS into a single HTML file
pytest tests/ --html=reports/test_report.html --self-contained-html --asyncio-mode=auto

echo ""
echo "========================================================"
echo "[DONE] Test Report Generated: reports/test_report.html"
echo "========================================================"
