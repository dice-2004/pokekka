#!/bin/bash
###############################################################
# 提出パッケージ構築スクリプト
#
# rl_drapa エージェントを Kaggle 提出用の tar.gz に
# パッケージングする。
#
# 使用方法:
#   bash agents_draft/rl_drapa/build_submission.sh
#
# 出力:
#   agents_draft/rl_drapa/submission.tar.gz
###############################################################
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="${SCRIPT_DIR}/submission.tar.gz"

echo "=== Building submission package ==="
echo "Source: ${SCRIPT_DIR}"

# 一時ディレクトリで作業
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# 必要なファイルをコピー
cp "${SCRIPT_DIR}/main.py" "${TMPDIR}/"
cp "${SCRIPT_DIR}/deck.csv" "${TMPDIR}/"
cp -r "${SCRIPT_DIR}/cg" "${TMPDIR}/"

# 学習済みモデルがあればコピー
if [ -f "${SCRIPT_DIR}/model.pt" ]; then
    cp "${SCRIPT_DIR}/model.pt" "${TMPDIR}/"
    echo "  Including model.pt"
fi

# RL モジュールをコピー（推論に必要なもののみ）
for f in config.py state_encoder.py action_encoder.py network.py reward.py; do
    if [ -f "${SCRIPT_DIR}/${f}" ]; then
        cp "${SCRIPT_DIR}/${f}" "${TMPDIR}/"
    fi
done

# __init__.py は不要（CWDベースでインポート）

# 不要ファイルの除外
rm -rf "${TMPDIR}/cg/__pycache__"
rm -rf "${TMPDIR}/__pycache__"

# tar.gz 作成
cd "${TMPDIR}"
tar -czf "${OUTPUT}" ./*

echo "  Package: ${OUTPUT}"
echo "  Size: $(du -h "${OUTPUT}" | cut -f1)"
echo "  Contents:"
tar -tzf "${OUTPUT}" | head -20
echo ""
echo "=== Build complete ==="
