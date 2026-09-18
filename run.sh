#!/usr/bin/env bash
# Launch DocMind. Run from the project root so `app.*` imports resolve.
set -e
cd "$(dirname "$0")"
echo "DocMind starting on http://127.0.0.1:8000  (Ctrl+C to stop)"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 "$@"
