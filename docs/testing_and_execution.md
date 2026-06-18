# 実行・テスト・検証マニュアル (docs/testing_and_execution.md)

本ドキュメントでは、エージェントの検証、対戦勝率の測定、および対戦過程のGUI可視化を実行するための各種テストスクリプトの使用方法について解説します。

ホスト側のファイル所有権（パーミッション）問題を防止するため、Docker 起動コマンドには必ず `--user $(id -u):$(id -g)` を付与して実行してください。

---

## 1. 動作検証テスト (Dry Run)

エージェントがシミュレータ上でエラーを起こさず、ルールに則って1ゲーム最後まで正常に対戦完了できるかをテストします。

### 1.1 検出された全エージェントの一括テスト (CIと同等)
引数なしで実行すると、`sample_submission/`、`agents_draft/` 配下に存在するすべての有効なエージェントフォルダを走査して順次テストします。
※完成済みフォルダである `agents/` は除外されます（`--include-completed` で含めることも可能）。

```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/dry_run.py
```

### 1.2 特定のエージェントを指定してテスト
```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/dry_run.py \
  --agent-dir agents_draft/my_agent
```

---

## 2. 対戦勝率測定ベンチマークテスト (Benchmark)

2つのエージェントを指定した回数対戦させ、勝率および平均ターン数を測定・集計します。
C++ ゲームエンジンのメモリリークやゲーム間の状態リークを防止するため、**1試合ごと別プロセスを立ち上げて完全に隔離実行**します。また、マルチプロセスによる並列対戦をサポートしています。

### 2.1 個別対戦 (特定エージェント同士)
```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/benchmark.py \
  --agent-a agents_draft/my_agent/main.py \
  --agent-b latest_submission/main.py \
  --matches 50 \
  --workers 4
```
- `--agent-a`: テストしたい新エージェントの `main.py` のパス
- `--agent-b`: 比較対象のエージェントの `main.py` のパス
- `--matches`: 総対戦回数 (偶数推奨、通常は 20〜50試合)
- `--workers`: 並列実行ワーカー数 (デフォルト: `CPUコア数 - 1`、`1` を指定すると並列化せずシングルプロセス同期実行)

### 2.2 ベースライン比較対戦
指定したベースラインエージェントと、検出されたすべてのエージェント（`sample_submission`, `agents_draft/*`）をそれぞれ対戦させます。
```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/benchmark.py \
  --baseline sample_submission/main.py \
  --matches 20
```

### 2.3 総当たり戦 (Round Robin)
検出されたすべてのエージェント間で総当たり戦を実行し、順位表（Tournament Standings）を出力します。
```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/benchmark.py \
  --round-robin \
  --matches 20
```

---

## 3. 対戦のビジュアル可視化 (Visualization)

対戦の様子を Kaggle 上と同一のビジュアル（アニメーション付きGUI）で再現・確認できる HTML ファイルを出力します。エージェントの意思決定のバグやプレイスタイルのデバッグに非常に有用です。

```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/visualize_match.py \
  --agent-a agents_draft/my_agent/main.py \
  --agent-b latest_submission/main.py \
  --output scratch/visualizer.html
```
- `--output`: 出力先HTMLファイルのパス（デフォルト: `scratch/visualizer.html`）

### 3.1 確認方法
コマンド実行後、生成された `scratch/visualizer.html` を Chrome などの Web ブラウザで開くだけで、対戦ログやカードの配置、ダメージの蓄積（ダメカン）などがGUIアニメーションで可視化されます。

---

## 4. 静的チェックのローカル実行 (CI同等)

GitHub にコミットをプッシュする前に、CI と同様のコードスタイルチェックをローカルで手動実行することができます。

```bash
# 存在する対象ファイルを動的にスキャンし、一意のファイルリストを作る
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev bash -c '
  PATHS="sample_submission/main.py latest_submission tests agents_draft agents"
  VALID_PATHS=""
  for p in $PATHS; do
    if [ -e "$p" ]; then
      VALID_PATHS="$VALID_PATHS $p"
    fi
  done
  CHECK_FILES=$(find $VALID_PATHS -name "*.py" -not -path "*/cg/*" 2>/dev/null | sort -u | xargs)
  
  echo "=== 1. Black Formatter Check ==="
  black --check $CHECK_FILES
  
  echo "=== 2. Flake8 Linter ==="
  flake8 $CHECK_FILES --count --select=E9,F63,F7,F82 --show-source --statistics
  
  echo "=== 3. Mypy Type Checker ==="
  mypy $CHECK_FILES --ignore-missing-imports --follow-imports=silent --explicit-package-bases
'
```
