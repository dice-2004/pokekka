#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

NO_LINT=false
POSITIONAL_ARGS=()
EXTRA_ARGS=()

# ループカウンタによるパース
args=("$@")
i=0
while [ $i -lt ${#args[@]} ]; do
  arg="${args[$i]}"
  if [ "$arg" = "--no-lint" ]; then
    NO_LINT=true
    i=$((i + 1))
  elif [[ "$arg" == --* ]]; then
    # オプション名を追加
    EXTRA_ARGS+=("$arg")
    
    # 次の引数が存在し、それがハイフンで始まらない場合は値とみなす
    next_idx=$((i + 1))
    if [ $next_idx -lt ${#args[@]} ]; then
      next_arg="${args[$next_idx]}"
      if [[ "$next_arg" != --* ]]; then
        EXTRA_ARGS+=("$next_arg")
        i=$((i + 2))
      else
        i=$((i + 1))
      fi
    else
      i=$((i + 1))
    fi
  else
    POSITIONAL_ARGS+=("$arg")
    i=$((i + 1))
  fi
done

# リンターの自動実行
if [ "$NO_LINT" = false ]; then
  echo "=== Running Linter before Visualization ==="
  bash "$PROJECT_ROOT/scripts/lint.sh"
  if [ $? -ne 0 ]; then
    echo -e "\e[31m[Error] Linter failed. Please fix style/type issues before visualization, or run with --no-lint to bypass.\e[0m"
    exit 1
  fi
fi

# デフォルト設定
if [ -f "$PROJECT_ROOT/latest_submission_path.txt" ]; then
  LATEST_DIR=$(cat "$PROJECT_ROOT/latest_submission_path.txt" | tr -d '\r' | xargs)
  AGENT_B="$LATEST_DIR/main.py"
else
  AGENT_B="latest_submission/main.py"
fi
OUTPUT="scratch/visualizer.html"

# エージェント解決関数
resolve_agent_file() {
  local input="$1"
  local resolved=""
  if [ -f "$PROJECT_ROOT/$input" ]; then
    resolved="$input"
  elif [ -f "$PROJECT_ROOT/$input/main.py" ]; then
    resolved="$input/main.py"
  else
    if [ -f "$PROJECT_ROOT/agents_draft/$input/main.py" ]; then
      resolved="agents_draft/$input/main.py"
    elif [ -f "$PROJECT_ROOT/agents/$input/main.py" ]; then
      resolved="agents/$input/main.py"
    else
      resolved="$input"
    fi
  fi
  echo "$resolved"
}

FINAL_ARGS=()

# 位置引数の数に応じた自動マッピング
NUM_POSITIONAL=${#POSITIONAL_ARGS[@]}
if [ $NUM_POSITIONAL -eq 1 ]; then
  # 1つの場合は agent-a に割り当て
  AGENT_A_RESOLVED=$(resolve_agent_file "${POSITIONAL_ARGS[0]}")
  FINAL_ARGS+=("--agent-a" "$AGENT_A_RESOLVED")
elif [ $NUM_POSITIONAL -ge 2 ]; then
  # 2つの場合は 1つ目を agent-a、2つ目を agent-b に割り当て
  AGENT_A_RESOLVED=$(resolve_agent_file "${POSITIONAL_ARGS[0]}")
  AGENT_B_RESOLVED=$(resolve_agent_file "${POSITIONAL_ARGS[1]}")
  FINAL_ARGS+=("--agent-a" "$AGENT_A_RESOLVED")
  FINAL_ARGS+=("--agent-b" "$AGENT_B_RESOLVED")
fi

has_arg() {
  for a in "${EXTRA_ARGS[@]}"; do
    if [[ "$a" == "$1"* ]]; then
      return 0
    fi
  done
  return 1
}

has_final_arg() {
  for a in "${FINAL_ARGS[@]}"; do
    if [[ "$a" == "$1"* ]]; then
      return 0
    fi
  done
  return 1
}

if ! has_final_arg "--agent-b" && ! has_arg "--agent-b"; then
  FINAL_ARGS+=("--agent-b" "$AGENT_B")
fi
if ! has_arg "--output"; then
  mkdir -p "$PROJECT_ROOT/scratch"
  FINAL_ARGS+=("--output" "$OUTPUT")
fi

FINAL_ARGS+=("${EXTRA_ARGS[@]}")
bash "$PROJECT_ROOT/scripts/run_in_env.sh" python tests/visualize_match.py "${FINAL_ARGS[@]}"
