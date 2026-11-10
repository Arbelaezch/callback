#!/usr/bin/env bash
# Real (non-mocked) tailoring check over the sample resumes. Spends Anthropic API credits.
# Usage: scripts/check-tailoring.sh [check_tailoring args]; defaults to the docs/test-resumes samples.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/backend"
export USE_S3=False
if [ "$#" -eq 0 ]; then
  set -- ../docs/test-resumes/*.pdf --job ../docs/test-resumes/job.txt --out ../docs/test-resumes/out/tailoring
fi
exec env/bin/python manage.py check_tailoring "$@"
