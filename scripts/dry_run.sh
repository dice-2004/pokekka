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
  echo "=== Running Linter before Dry Run ==="
  bash "$PROJECT_ROOT/scripts/lint.sh"
  if [ $? -ne 0 ]; then
    echo -e "\e[31m[Error] Linter failed. Please fix style/type issues before dry run, or run with --no-lint to bypass.\e[0m"
    exit 1
  fi
fi

# パス解決
FINAL_ARGS=()
if [ -n "$AGENT_ARG" ]; then
  # 1. ファイルが指定された場合は、その親ディレクトリを設定
  if [ -f "$PROJECT_ROOT/$AGENT_ARG" ]; then
    RESOLVED_DIR=$(dirname "$AGENT_ARG")
  # 2. 直接ディレクトリが存在する場合 (例: agents/my_agent, agents_draft/my_agent, latest_submission)
  elif [ -d "$PROJECT_ROOT/$AGENT_ARG" ]; then
    RESOLVED_DIR="$AGENT_ARG"
  # 3. 単にフォルダ名のみが指定された場合 (例: my_agent)
  else
    if [ -d "$PROJECT_ROOT/agents_draft/$AGENT_ARG" ]; then
      RESOLVED_DIR="agents_draft/$AGENT_ARG"
    elif [ -d "$PROJECT_ROOT/agents/$AGENT_ARG" ]; then
      RESOLVED_DIR="agents/$AGENT_ARG"
    else
      RESOLVED_DIR="$AGENT_ARG"
    fi
  fi
  
  FINAL_ARGS+=("--agent-dir" "$RESOLVED_DIR")
fi

FINAL_ARGS+=("${EXTRA_ARGS[@]}")
bash "$PROJECT_ROOT/scripts/run_in_env.sh" python tests/dry_run.py "${FINAL_ARGS[@]}"
