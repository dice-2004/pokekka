# 実行・テスト・検証マニュアル (docs/testing_and_execution.md)

本ドキュメントでは、エージェントの検証、対戦勝率の測定、および対戦過程のGUI可視化を実行するための各種テストスクリプトの使用方法について解説します。

本プロジェクトでは、すべての検証・テストコマンドを **VS Code Dev Container (コンテナ内) で実行**します。コンテナ環境内では、自動的に各種スクリプトへの実行パス（`PATH`）が通っているため、`bash` や `scripts/` のプリフィックスを付けず、直接コマンド名を入力するだけで実行できます。

---

## 0. 実行の前提 (PATH 設定の確認)

コンテナ内のターミナルであれば、どのディレクトリにいても直接スクリプトを実行できます。

*   **コマンド例**: `dry_run.sh my_agent`
*   *※注意*: `devcontainer.json` の変更を反映させるには、コンテナを一度再起動（または「**Rebuild Container (コンテナの再構築)**」）するか、ターミナルで `source ~/.bashrc` を実行して環境変数を更新してください。

---

## 1. 動作検証テスト (Dry Run)

エージェントがシミュレータ上でエラーを起こさず、ルールに則って1ゲーム最後まで正常に対戦完了できるかをテストします。

※テスト実行前に、自動的に PR 時に動作するリンター（Black, Flake8, Mypy）と同等の静的チェックが走ります。エラーがある場合はテストは実行されません（`--no-lint` オプションでスキップ可能です）。

### 1.1 全エージェントの一括テスト
引数なしで実行すると、`sample_submission/`、`agents_draft/` 配下のすべての有効なエージェントを走査して検証します。

```bash
dry_run.sh
```

### 1.2 特定のエージェントを指定してテスト
位置引数にエージェント名を指定します。`agents/my_agent` や `agents_draft/my_agent` などのディレクトリパスのほか、単にフォルダ名 `my_agent` を入力した場合も自動的にパスを補完・解決します。

```bash
dry_run.sh my_agent
```

---

## 2. 対戦勝率測定ベンチマークテスト (Benchmark)

2つのエージェントを指定した回数対戦させ、勝率および平均ターン数を測定・集計します。

※テスト実行前に、自動的に静的チェックが走ります（`--no-lint` でスキップ可能です）。
※比較相手（デフォルト: `latest_submission`）、対戦数（デフォルト: `50`）、並列プロセス数（デフォルト: `4`）が自動適用されるため、ハイフン付きのオプションを打たずに**位置引数のみで簡潔に実行**できます。

### 2.1 個別対戦 (位置引数による指定)

#### パターン A: 1つのエージェントのみ指定する (デフォルトの latest_submission と 50 試合対戦)
```bash
benchmark.sh my_agent
```

#### パターン B: 2つのエージェントを指定して対戦させる
位置引数に2つ並べて指定します。自動的に1つ目がテスト対象（`agent-a`）、2つ目が比較対象（`agent-b`）にマッピングされます。
```bash
benchmark.sh my_agent other_agent
```
*※上記の場合、`my_agent` と `other_agent` を 50 試合対戦させます。*

#### パターン C: オプション設定を上書きして実行する場合 (例: 10試合対戦、並列2プロセス)
```bash
benchmark.sh my_agent other_agent --matches 10 --workers 2
```

### 2.2 ベースライン比較対戦
指定したベースラインと、検出されたすべてのエージェントを対戦させます。
```bash
benchmark.sh --baseline sample_submission/main.py --matches 20
```

### 2.3 総当たり戦 (Round Robin)
検出されたすべてのエージェント間で総当たり戦を実行し、順位表（Tournament Standings）を出力します。
```bash
benchmark.sh --round-robin --matches 20
```

---

## 3. 対戦のビジュアル可視化 (Visualization)

対戦の様子を Kaggle と同じGUI（アニメーション付き可視化ビューア）で再現できる HTML ファイルを出力します。

※テスト実行前に、自動的に静的チェックが走ります（`--no-lint` でスキップ可能です）。
※デフォルトの比較相手（`latest_submission`）および出力先（`scratch/visualizer.html`）が内包されています。

### 3.1 デフォルトの相手 (latest_submission) との可視化対戦
```bash
visualize.sh my_agent
```

### 3.2 特定のエージェント同士の可視化対戦
位置引数に2つのエージェントを並べて指定します。
```bash
visualize.sh my_agent other_agent
```
*※生成された `scratch/visualizer.html` を Chrome などのブラウザで開くことで、対戦を可視化再生できます。*

---

## 4. 静的チェックのローカル実行 (Linter & Type Checker)

コミット前に、CI と同様のコードスタイルチェック（Black, Flake8, Mypy）を手動実行することができます。

```bash
lint.sh
```

### 4.1 Black による自動コードフォーマット
スタイル違反箇所を自動修正・整形したい場合は、`--fix` オプションを付与します。
```bash
lint.sh --fix
```
