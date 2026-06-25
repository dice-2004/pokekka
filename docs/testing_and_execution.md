# 実行・テスト・検証マニュアル (docs/testing_and_execution.md)

本ドキュメントでは、エージェントの検証、対戦勝率の測定、および対戦過程のGUI可視化を実行するための各種テストスクリプトの使用方法について解説します。

提供されている `scripts/` 配下のスクリプトは、実行環境（ホスト / コンテナ内）の自動判定や、パーミッション調整、よく使う引数の内包などを自動で行うため、非常に簡単にテストを実行できます。

---

## 1. 動作検証テスト (Dry Run)

エージェントがシミュレータ上でエラーを起こさず、ルールに則って1ゲーム最後まで正常に対戦完了できるかをテストします。

※テスト実行前に、自動的に PR 時に動作するリンター（Black, Flake8, Mypy）と同等の静的チェックが走ります。静的チェックでエラーが検出された場合はテストは実行されません（`--no-lint` オプションでスキップ可能です）。

### 1.1 検出された全エージェントの一括テスト (CIと同等)
引数なしで実行すると、`sample_submission/`、`agents_draft/` 配下に存在するすべての有効なエージェントフォルダを走査して順次テストします。

```bash
bash scripts/dry_run.sh
```

### 1.2 特定のエージェントを指定してテスト
エージェント名（フォルダ名）だけを直接指定してテストできます（自動的に `agents_draft/` 配下を解決します）。

```bash
bash scripts/dry_run.sh my_agent
```

---

## 2. 対戦勝率測定ベンチマークテスト (Benchmark)

2つのエージェントを指定した回数対戦させ、勝率および平均ターン数を測定・集計します。

※テスト実行前に、自動的に静的チェックが走ります（`--no-lint` でスキップ可能です）。
※よく使うオプション（対戦相手のデフォルト：`latest_submission`、対戦数：`50`、並列ワーカー数：`4`）があらかじめ内包されているため、エージェント名のみの簡易指定で実行できます。

### 2.1 個別対戦 (特定エージェント同士)

#### 基本的な実行（デフォルト設定：latest_submission と 50 試合対戦）
```bash
bash scripts/benchmark.sh my_agent
```

#### 設定を上書きして実行する場合（例：10試合対戦、並列2プロセス）
```bash
bash scripts/benchmark.sh my_agent --matches 10 --workers 2
```

#### 比較エージェントを明示的に指定して実行する場合
```bash
bash scripts/benchmark.sh my_agent --agent-b sample_submission/main.py
```

### 2.2 ベースライン比較対戦
指定したベースラインエージェントと、検出されたすべてのエージェントをそれぞれ対戦させます。
```bash
bash scripts/benchmark.sh --baseline sample_submission/main.py --matches 20
```

### 2.3 総当たり戦 (Round Robin)
検出されたすべてのエージェント間で総当たり戦を実行し、順位表（Tournament Standings）を出力します。
```bash
bash scripts/benchmark.sh --round-robin --matches 20
```

---

## 3. 対戦のビジュアル可視化 (Visualization)

対戦の様子を Kaggle 上と同一のビジュアル（アニメーション付きGUI）で再現・確認できる HTML ファイルを出力します。

※デフォルトの比較相手（`latest_submission/main.py`）および出力先（`scratch/visualizer.html`）が内包されているため、エージェント名のみの指定で実行できます。

```bash
bash scripts/visualize.sh my_agent
```

### 3.1 確認方法
コマンド実行後、生成された `scratch/visualizer.html` を Chrome などの Web ブラウザで開くだけで、対戦ログやカードの配置、ダメカンなどがGUIアニメーションで可視化されます。

---

## 4. 静的チェックのローカル実行 (Linter & Type Checker)

GitHub にコミットをプッシュする前に、CI と同様のコードスタイルチェック（Black, Flake8, Mypy）をローカルで手動実行することができます。

```bash
# リンターと型チェックを実行
bash scripts/lint.sh
```

### 4.1 Black による自動コードフォーマット
コードのスタイルエラーを自動で修正・整形したい場合は、`--fix` オプションを付けて実行します。

```bash
# 自動コードフォーマットを実行
bash scripts/lint.sh --fix
```
