#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

NO_LINT=false
AGENT_ARG=""
EXTRA_ARGS=()

for arg in "$@"; do
  if [ "$arg" = "--no-lint" ]; then
    NO_LINT=true
  elif [[ "$arg" == --* ]]; then
    EXTRA_ARGS+=("$arg")
  else
    AGENT_ARG="$arg"
  fi
done

# リンターの自動実行
if [ "$NO_LINT" = false ]; then
  echo "=== Running Linter before Benchmark ==="
  bash "$PROJECT_ROOT/scripts/lint.sh"
  if [ $? -ne 0 ]; then
    echo -e "\e[31m[Error] Linter failed. Please fix style/type issues before benchmark, or run with --no-lint to bypass.\e[0m"
    exit 1
  fi
fi

# デフォルト設定
AGENT_B="latest_submission/main.py"
MATCHES="50"
WORKERS="4"

# パス解決
FINAL_ARGS=()
if [ -n "$AGENT_ARG" ]; then
  # 1. main.py ファイルを直接指している場合
  if [ -f "$PROJECT_ROOT/$AGENT_ARG" ]; then
    RESOLVED_FILE="$AGENT_ARG"
  # 2. ディレクトリを指しており、その配下に main.py が存在する場合
  elif [ -f "$PROJECT_ROOT/$AGENT_ARG/main.py" ]; then
    RESOLVED_FILE="$AGENT_ARG/main.py"
  # 3. 単にフォルダ名のみが指定された場合 (例: my_agent)
  else
    if [ -f "$PROJECT_ROOT/agents_draft/$AGENT_ARG/main.py" ]; then
      RESOLVED_FILE="agents_draft/$AGENT_ARG/main.py"
    elif [ -f "$PROJECT_ROOT/agents/$AGENT_ARG/main.py" ]; then
      RESOLVED_FILE="agents/$AGENT_ARG/main.py"
    else
      RESOLVED_FILE="$AGENT_ARG"
    fi
  fi
  
  FINAL_ARGS+=("--agent-a" "$RESOLVED_FILE")
fi

has_arg() {
  for a in "${EXTRA_ARGS[@]}"; do
    if [[ "$a" == "$1"* ]]; then
      return 0
    fi
  done
  return 1
}

if ! has_arg "--agent-b"; then
  FINAL_ARGS+=("--agent-b" "$AGENT_B")
fi
if ! has_arg "--matches"; then
  FINAL_ARGS+=("--matches" "$MATCHES")
fi
if ! has_arg "--workers"; then
  FINAL_ARGS+=("--workers" "$WORKERS")
fi

FINAL_ARGS+=("${EXTRA_ARGS[@]}")
bash "$PROJECT_ROOT/scripts/run_in_env.sh" python tests/benchmark.py "${FINAL_ARGS[@]}"
