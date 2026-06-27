#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$PROJECT_ROOT/scripts/run_in_env.sh" python tests/update_cg.py "$@"
