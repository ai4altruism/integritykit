#!/bin/bash
# Test runner script for Aid Arena Integrity Kit

set -e

echo "=== Aid Arena Integrity Kit Test Suite ==="
echo

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "Running all tests..."
pytest tests/ -v --tb=short

echo
echo "=== Test Summary ==="
echo "Unit tests (fast):"
pytest -m unit -q --tb=line

echo
echo "Integration tests:"
pytest -m integration -q --tb=line

echo
echo "=== Coverage Report ==="
pytest tests/ --cov=integritykit --cov-report=term-missing --cov-report=html -q

echo
echo "All tests passed! HTML coverage report: htmlcov/index.html"
