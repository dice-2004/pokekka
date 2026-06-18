# Docker 開発環境 設計仕様書

本仕様書は、チームメンバー全員が同一の環境で安全かつ容易にポケモンカードAIエージェントの開発およびテストを行えるよう、Docker および VS Code Dev Containers を用いた共通開発環境の設計を定義したものです。

---

## 1. 開発環境の要件

- **Python バージョン**: 3.10 (Kaggle公式および cabt エンジンの推奨環境に準拠)
- **ホストOS対応**: Windows, macOS (Intel/Apple Silicon), Linux
- **必須パッケージ**:
  - `kaggle-environments`
  - `black`, `flake8`, `mypy` (静的解析用)
  - `ipykernel` (Jupyter Notebook用)

---

## 2. Docker イメージ構成

Kaggleシミュレーション用に最適化された Python 環境をベースとします。
Apple Silicon Mac (M1/M2/M3) で Linux x86_64 用の `libcg.so` をロードさせるため、プラットフォームを `linux/amd64` に強制指定します。

### 2.1 Dockerfile (`.devcontainer/Dockerfile`)
```dockerfile
FROM --platform=linux/amd64 python:3.10-slim

# システムパッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ
WORKDIR /workspace

# Python パッケージのインストール
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    kaggle-environments \
    black \
    flake8 \
    mypy \
    ipykernel \
    numpy \
    pandas

CMD ["bash"]
```

### 2.2 Devcontainer 設定 (`.devcontainer/devcontainer.json`)
VS Code の拡張機能「Dev Containers」を利用して、エディタ設定や必要な拡張機能（Python, Pylance, Jupyter, GitLens 等）をコンテナ起動時に自動セットアップします。

```json
{
  "name": "PTCG AI Battle Challenge Dev Env",
  "build": {
    "dockerfile": "Dockerfile",
    "context": ".."
  },
  "customizations": {
    "vscode": {
      "settings": {
        "python.defaultInterpreterPath": "/usr/local/bin/python",
        "python.linting.enabled": true,
        "python.linting.flake8Enabled": true,
        "python.formatting.provider": "black",
        "editor.formatOnSave": true
      },
      "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-toolsai.jupyter",
        "donjayamanne.githistory"
      ]
    }
  },
  "postCreateCommand": "echo 'Container initialized. Ready for development!'",
  "remoteUser": "root"
}
```

---

## 3. コンテナを使用するメリットとデメリット

| 項目 | メリット | デメリット |
| :--- | :--- | :--- |
| **環境差の排除** | 「自分のPCでは動くのに他のPCで動かない」という問題を防止できる。 | 初回のコンテナビルド（Dockerイメージダウンロードなど）に数分かかる。 |
| **他OSのサポート** | `libcg.so` が Linux x86_64 用であるため、Apple Silicon Mac などの環境でも `--platform=linux/amd64` 指定でエミュレーション動作可能。 | Apple Silicon Mac上で Intel(x86_64) エミュレーションを行うため、実行・学習速度がネイティブに比べてやや低下する。 |
| **チーム内の即時立ち上げ** | VS Codeでクローンして「Reopen in Container」を押すだけで自動で環境構築が完了する。 | 各自のPCに Docker Desktop (または Rancher Desktop, Colima 等) のインストールが必要。 |
