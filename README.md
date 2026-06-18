# ポケモンカードゲーム AI バトルチャレンジ 開発マニュアル (README.md)

本プロジェクトは、Kaggleで開催される「ポケモンカードゲーム AI バトルチャレンジ」に向けた AI エージェント開発リポジトリです。
本ドキュメントでは、開発環境の構築、テストの実行、対戦の可視化、および GitHub での共同開発フローについて解説します。

---

## 1. プロジェクトの構成

```text
├── .agents/
│   └── AGENTS.md          # AI 開発ガイドライン (最重要ルール)
├── .devcontainer/
│   ├── Dockerfile         # 共通開発用 Dockerfile (UID/GID マッピング対応)
│   └── devcontainer.json  # VS Code 用開発コンテナ構成設定
├── .github/
│   └── workflows/
│       ├── ci.yml         # PR作成時のコード品質・動作検証 (CI)
│       ├── benchmark.yml  # PR作成時の新旧エージェント自動勝率測定
│       └── archive_agent.yml # マージ時のエージェント自動アーカイブ (移動)
├── agents_draft/          # 🔧 開発・作業中のエージェントフォルダ (PR対戦対象)
├── agents/                # ✅ 完成・マージ済みのエージェントフォルダ
├── latest_submission/     # 🏆 現在の提出予定エージェント (PR対戦相手)
├── sample_submission/     # テンプレート (コピー元・直接編集しない)
│   ├── main.py
│   ├── deck.csv
│   └── cg/
├── tests/                 # ローカル検証・CI用テストスクリプト
│   ├── fetch_samples.py   # 公式サンプル自動取得ツール (Kaggle API利用)
│   ├── dry_run.py         # 動作検証テスト
│   ├── benchmark.py       # 勝率測定ベンチマークテスト (並列処理・プロセス隔離内蔵)
│   └── visualize_match.py # 対戦可視化ツール (HTMLビューアの出力)
├── scratch/               # 可視化 HTML などが一時的に出力されるディレクトリ
├── LOG.md                 # 開発作業ログ (変更のたびに要記録)
└── README.md              # 本ドキュメント (各種構築・実行マニュアル)
```

---

## 2. 環境構築手順

開発環境には **Docker** を使用します。共有ライブラリ `libcg.so` が Linux (x86_64) バイナリであるため、Docker コンテナを利用することで OS（Windows, Mac, Linux）を問わず同一の検証環境を構築できます。

### 方法 A: VS Code Dev Containers を使用する (推奨)
1. VS Code に拡張機能「**Dev Containers**」をインストールします。
2. 本プロジェクトフォルダを VS Code で開きます。
3. 画面右下に表示される「**Reopen in Container (コンテナで開く)**」をクリックします。
4. 自動的に Docker イメージがビルドされ、コンテナ内で開発準備が完了します。
   *(Black などのフォーマッタや Flake8 リンタ、Python/Jupyter 等の拡張機能も自動セットアップされます)*

### 方法 B: 手動で Docker イメージをビルドする
VS Code を使わない、またはターミナルから直接コマンドを実行する場合は、手動でイメージをビルドします。
```bash
# プロジェクトのルートディレクトリで実行
docker build -t ptcg-dev -f .devcontainer/Dockerfile .
```

---

## 3. 公式サンプルエージェントの取得手順

Kaggle で公開されている公式サンプルエージェント（Lucario, Abomasnow, Dragapult, Iono）を一括で自動ダウンロードし、`agents_draft/` 配下に配置するスクリプトが用意されています。

### 事前準備: Kaggle API トークンの設定
本ツールの利用には Kaggle API トークンが必要です。
1. Kaggleアカウントの Settings ページから「Create New Token」を実行し、`kaggle.json` をダウンロードします。
2. ホストマシンのユーザーホームディレクトリの下に配置します：
   - Windows: `C:\Users\<ユーザー名>\.kaggle\kaggle.json`
   - macOS/Linux: `~/.kaggle/kaggle.json`

### サンプル取得の実行方法
インストール時の権限エラーを防ぐため、コンテナを **root 権限** で起動してスクリプトを実行します。
```bash
# ホスト側の ~/.kaggle をコンテナの /root/.kaggle にマウントして実行
docker run --rm -v $(pwd):/workspace -w /workspace -v ~/.kaggle:/root/.kaggle:ro ptcg-dev python3 tests/fetch_samples.py
```
ダウンロードされたエージェントは自動で `agents_draft/` 配下に展開され、同時に最新の `cg` フォルダが同期されます。

---

## 3. テストと動作確認の方法

ホスト側のファイル所有権（パーミッション）問題を防止するため、Docker 起動コマンドには必ず `--user $(id -u):$(id -g)` を付与して実行してください。

### ① 動作検証テスト (Dry Run)
エージェントがシミュレータ上でエラーを起こさず、ルールに則って1ゲーム最後まで正常に対戦完了できるかをテストします。
```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/dry_run.py
```
*   **用途**: コード変更後に、Syntaxエラーや実行時例外が起きないかを即座に確認するために使用します。

### ② 勝率測定ベンチマークテスト (Benchmark)
2つのエージェントを指定した回数対戦させ、勝率を測定・集計します。
C++ ゲームエンジンのメモリリークを防ぐため、1試合ごとプロセスを完全に隔離して実行します。また、マルチプロセスによる並列対戦をサポートしています。
```bash
# 例：エージェントA と エージェントB を 4ワーカー並列で 50試合対戦させる場合
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/benchmark.py \
  --agent-a agents_draft/my_agent/main.py \
  --agent-b latest_submission/main.py \
  --matches 50 \
  --workers 4
```
*   **引数**:
    *   `--agent-a`: テストしたい新エージェントの `main.py` のパス
    *   `--agent-b`: 比較対象のエージェントの `main.py` のパス
    *   `--matches`: 対戦回数 (偶数推奨、通常は 20〜50試合)
    *   `--workers`: 並列実行ワーカー数 (デフォルト: `CPUコア数 - 1`、`1` を指定するとシングルプロセス同期実行)
*   **特徴**: プロセス隔離による状態リーク防止の他、環境内のゲームエンジン自動パッチ、二重ロード防止機能、`tqdm` による進捗表示バーを内蔵しています。

### ③ 対戦のビジュアル可視化 (Visualization)
対戦の様子を Kaggle 上と同一のビジュアル（アニメーション付きGUI）で再現・確認できる HTML ファイルを出力します。
```bash
docker run --rm --user $(id -u):$(id -g) -v $(pwd):/workspace -w /workspace ptcg-dev python tests/visualize_match.py \
  --agent-a sample_submission/main.py \
  --agent-b sample_submission/main.py \
  --output scratch/visualizer.html
```
*   **確認方法**:
    コマンド実行完了後、生成された `scratch/visualizer.html` を Chrome などの Web ブラウザで開くだけで、対戦ログやカードの配置、ダメージの蓄積（ダメカン）などがGUIで可視化されます。
*   **注意（パーミッションエラー時の対処法）**:
    以前に `docker run` を `--user` 指定なし（または root 権限）で実行していた場合、`scratch/` ディレクトリの所有者が `root` になり、一般ユーザーで書き込めず `PermissionError` が出ることがあります。
    その場合は、ホスト側のターミナルで `rm -rf scratch && mkdir scratch` を実行して、ディレクトリをユーザー所有権で再作成してください。

---

## 4. チーム開発フローと GitHub Actions (CI/CD)

チームで安全かつ整合性を保って開発を進めるため、以下のフローに沿って作業を行います。

### Step 1: 開発用ブランチでの作業とローカルテスト
1. `main` ブランチから機能ごとの開発ブランチを作成します。
2. 作業を行い、コード品質チェックや動作テストを実行します。
3. コードの変更を行った際は、必ず **[LOG.md](LOG.md)** の最上部に「作業内容」「実装の意図」「検証結果」を記録します。

### Step 2: プルリクエスト (PR) の作成
開発が完了したら `main` ブランチに対して PR を作成します。PR を作成すると、GitHub Actions が以下の2つのワークフローを自動的に並行実行します。

1.  **CI Validation ([ci.yml](.github/workflows/ci.yml))**:
    コードフォーマット（`black`）、リンター（`flake8`）、型チェック（`mypy`）、および動作検証テスト（`dry_run.py`）を実行し、マージ可能なコード品質であるかをチェックします。
2.  **Agent Battle Benchmark ([benchmark.yml](.github/workflows/benchmark.yml))**:
    PRブランチの `main.py` と、現在の `main` ブランチの `main.py` を自動で **20試合対戦** させ、勝率を自動計測します。結果は PR の会話スレッドに**勝率レポートテーブルとして自動投稿**されます。これにより、その変更でエージェントがどれほど強くなったか（デグレードしていないか）を定量評価できます。

### Step 3: レビューとマージ
テストがすべてグリーンになり、勝率の向上が確認されたらマージを行います。マージされると、再度 `ci.yml` が走り、最終的な品質チェックが自動で行われます。

---

## 5. 提出パッケージの作成方法

Kaggle にアップロードして提出するファイルは、必ず以下の構成で `.tar.gz` 形式に圧縮されている必要があります。

### 提出物の構成 (重要)
```text
submission.tar.gz/
├── main.py        # 提出用メインコード ( sample_submission/main.py からコピー )
├── deck.csv        # デッキ構成ファイル ( sample_submission/deck.csv からコピー )
└── cg/             # シミュレータ API ディレクトリ ( sample_submission/cg/ を丸ごとコピー )
```
*   **注意**: `tests/` ディレクトリや `.github/`、`.devcontainer/` などの開発・テスト用ファイルは、提出アーカイブに**絶対に含めない**でください。また、`main.py` がネストされたフォルダ内に配置されていると、Kaggle上でエラーになります。

### 圧縮コマンド例
```bash
# sample_submission ディレクトリに移動し、そこで圧縮を行います
cd sample_submission
tar -czvf ../submission.tar.gz main.py deck.csv cg/
```
作成された `submission.tar.gz` を Kaggle のコンペティションページの **"My Submissions"** タブからアップロードしてください。

---

## 6. 開発における最重要ルール (AGENTS.md)
AIの開発方針、APIの正確な使い方、時間制限 (600秒ルール) に関する仕様などは、**[.agents/AGENTS.md](.agents/AGENTS.md)** にすべてまとめられています。
コードを追加・修正する前には、必ずこのガイドラインを読み込み、レギュレーションに準拠した実装を行ってください。

## 7. 別エージェント開発の流れ

1. **作業エージェントの新規作成**:
   `sample_submission/` をコピーして、`agents_draft/` 配下に新しい作業フォルダを作成します。
   （または `tests/fetch_samples.py` を実行して、公式サンプルを `agents_draft/` に落としてきてそれを改造します）
2. **対戦検証**:
   `tests/benchmark.py` を用いて、作成した作業エージェントと `latest_submission/` (現在の最強候補) を戦わせます。
3. **PRの作成と勝率自動測定**:
   `agents_draft/` 内の変更をPRとして出すと、CI上で自動的に `latest_submission/` との対戦ベンチマークが走り、勝率がスレッドに投稿されます。
4. **マージと自動移動 (Archiving)**:
   PRがマージされると、対象のエージェントは GitHub Actions によって自動的に完成済みフォルダである `agents/` に移動され、`agents_draft/` 配下からは自動で削除されます。
