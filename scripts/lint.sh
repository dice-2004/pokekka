#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 引数のパース
FIX_MODE=false
INSIDE=false
for arg in "$@"; do
  if [ "$arg" = "--fix" ]; then
    FIX_MODE=true
  fi
  if [ "$arg" = "--inside" ]; then
    INSIDE=true
  fi
done

if [ "$INSIDE" = true ]; then
    # コンテナ内での実際の実行ロジック
    PATHS="sample_submission/main.py latest_submission tests agents_draft agents"
    VALID_PATHS=""
    for p in $PATHS; do
      if [ -e "$PROJECT_ROOT/$p" ]; then
        VALID_PATHS="$VALID_PATHS $p"
      fi
    done
    
    cd "$PROJECT_ROOT"
    CHECK_FILES=$(find $VALID_PATHS -name "*.py" -not -path "*/cg/*" 2>/dev/null | sort -u | xargs)

    if [ -z "$CHECK_FILES" ]; then
        echo "No Python files found to lint."
        exit 0
    fi

    # 1. Black Check/Format
    if [ "$FIX_MODE" = true ]; then
        echo "=== Running Black Formatter (Auto-Fix) ==="
        black $CHECK_FILES
    else
        echo "=== Running Black Formatter Check ==="
        black --check $CHECK_FILES || exit 1
    fi

    # 2. Flake8 Linter
    echo "=== Running Flake8 Linter ==="
    flake8 $CHECK_FILES --count --select=E9,F63,F7,F82 --show-source --statistics || exit 1
    flake8 $CHECK_FILES --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

    # 3. Mypy Type Checker
    echo "=== Running Mypy Type Checker ==="
    mypy $CHECK_FILES --ignore-missing-imports --follow-imports=silent --explicit-package-bases || exit 1

else
    # ホスト側からの呼び出し：run_in_env.sh 経由で自分自身を --inside オプション付きで呼び出す
    PASSED_ARGS=("--inside")
    if [ "$FIX_MODE" = true ]; then
        PASSED_ARGS+=("--fix")
    fi
    bash "$PROJECT_ROOT/scripts/run_in_env.sh" bash "scripts/lint.sh" "${PASSED_ARGS[@]}"
fi
