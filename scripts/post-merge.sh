#!/usr/bin/env bash
# Safe, non-interactive checks for the current dependency-free safety model.
# Dependency/schema changes require explicit setup additions; never migrate
# financial data or contact a broker from this hook.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "Running software-only safety acceptance tests"
python -m unittest discover -s tests -p 'test_safety_spec.py' -v

echo "Rebuilding the frontend served by FastAPI"
npm --prefix frontend run build

echo "Post-merge setup complete"