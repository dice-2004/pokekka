#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# コンテナ内判定
is_container() {
    if [ -f /.dockerenv ] || grep -qiE 'docker|lxc|kubepods' /proc/1/cgroup 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

if is_container; then
    # コンテナ内であれば、直接コマンドを実行
    cd "$PROJECT_ROOT"
    exec "$@"
else
    # ホスト側であれば、コンテナ経由で実行する
    # 1. VS Code Dev Container が既に起動しているか確認
    if docker ps --format '{{.Names}}' | grep -q "pole.*devcontainer" 2>/dev/null; then
        CONTAINER_NAME=$(docker ps --format '{{.Names}}' | grep "pole.*devcontainer" | head -n 1)
        docker exec -it "$CONTAINER_NAME" "$@"
    else
        # 2. 起動中のコンテナがなければ docker run で一時コンテナを起動して実行
        KAGGLE_MOUNT=""
        if [ -d "$HOME/.kaggle" ]; then
            KAGGLE_MOUNT="-v $HOME/.kaggle:/root/.kaggle:ro"
        fi
        
        docker run --rm -it \
            --user "$(id -u):$(id -g)" \
            -v "$PROJECT_ROOT:/workspace" \
            -w /workspace \
            $KAGGLE_MOUNT \
            ptcg-dev "$@"
    fi
fi
