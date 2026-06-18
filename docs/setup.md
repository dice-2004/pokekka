# 開発環境セットアップマニュアル (docs/setup.md)

本ドキュメントでは、ポケモンカードゲーム AI エージェント開発のための共通開発環境の構築方法について解説します。
本プロジェクトでは、OS間の環境差異（特にC++共有ライブラリ `libcg.so` の動作環境）を排除するため、**Docker** および **VS Code Dev Containers** を用いた共通開発環境を使用します。

---

## 1. 開発環境の前提要件

- **Python バージョン**: 3.10 (Kaggle公式および cabt エンジンの推奨環境に準拠)
- **ホストOS**: Linux, Windows, macOS
- **必須ソフトウェア**:
  - Docker Desktop (または Colima, Rancher Desktop 等 of Docker 互換環境)
  - VS Code (推奨) + 拡張機能「**Dev Containers**」

---

## 2. 環境構築手順

### 方法 A: VS Code Dev Containers を使用する (推奨)

VS Code の拡張機能を使用すると、エディタ設定や必要なツール（Black などのフォーマッタ、Flake8 リンター、Python/Jupyter 用拡張機能）がコンテナ起動時に自動でセットアップされます。

1. VS Code に拡張機能「**Dev Containers**」をインストールします。
2. 本プロジェクトフォルダを VS Code で開きます。
3. 画面右下に表示される「**Reopen in Container (コンテナで開く)**」というポップアップをクリックします。
   - もし表示されない場合は、左下の緑色のマーク（`><`）をクリックし、「**Reopen in Container**」を選択します。
4. 自動的に Docker イメージがビルドされ、コンテナ内で開発準備が完了します。

### 方法 B: 手動で Docker イメージをビルドする

VS Code を使わない場合や、コマンドラインから直接コンテナを実行する場合は、手動でイメージをビルドします。

```bash
# プロジェクトのルートディレクトリで実行
docker build -t ptcg-dev -f .devcontainer/Dockerfile .
```

---

## 3. Kaggle API と公式サンプルの取得手順

Kaggle で公開されている公式サンプルエージェント（Lucario, Abomasnow, Dragapult, Iono）を一括で自動ダウンロードし、`sample_deck/` 配下に配置するスクリプトが用意されています。

### 3.1 事前準備: Kaggle API トークンの設定
本ツールの利用には Kaggle API トークンが必要です。
1. KaggleのSettingsページなどからアクセストークン（`KGA_`から始まる文字列）を取得します。
2. ホストマシンのユーザーホームディレクトリ配下に `access_token` というファイル名でトークンを直接書き込んで保存します：
   - Windows: `C:\Users\<ユーザー名>\.kaggle\access_token`
   - macOS/Linux: `~/.kaggle/access_token`

### 3.2 サンプル取得の実行方法
インストール時の権限エラーを防ぐため、コンテナを **root 権限** で起動してスクリプトを実行します。

```bash
# ホスト側の ~/.kaggle をコンテナの /root/.kaggle にマウントして実行
docker run --rm -v $(pwd):/workspace -w /workspace -v ~/.kaggle:/root/.kaggle:ro ptcg-dev python3 tests/fetch_samples.py
```

実行が完了すると、ダウンロードされたエージェントは自動で `sample_deck/` 配下に展開され、同時に最新の `cg` フォルダが自動で同期されます。

---

## 4. トラブルシューティング（パーミッションエラー）

ホスト側のファイル所有権（パーミッション）問題を防止するため、Docker 起動コマンドには原則として `--user $(id -u):$(id -g)` を付与して実行してください。

もし以前に `docker run` を `--user` 指定なし（または root 権限）で実行したことにより、`scratch/` などのディレクトリやファイルが書き込み禁止（所有者が `root`）になってしまった場合は、ホスト側のターミナルで以下を実行して所有権を戻すか再作成してください。

```bash
# 所有権の復元（Linux/macOS）
sudo chown -R $(id -u):$(id -g) scratch/

# またはディレクトリの再作成
rm -rf scratch && mkdir scratch
```
