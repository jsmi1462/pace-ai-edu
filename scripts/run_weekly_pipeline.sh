#!/bin/bash
# Weekly pipeline — runs every Sunday at 12:01 AM for all teachers.
# Fetches ERIC + RSS, embeds, evaluates, writes matches to DB.
# Articles are ready on each teacher's digest page by Monday morning.

set -e
cd /Users/compsci/pace-ai-edu

PYTHON="${PYTHON_BIN:-python3}"
exec $PYTHON -m pipeline.workflow
