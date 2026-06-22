FROM python:3.10-slim

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
    pandas && \
    chmod -R a+w /usr/local/lib/python3.10/site-packages

CMD ["bash"]
