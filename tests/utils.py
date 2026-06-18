"""テストおよびベンチマーク用共通ユーティリティ"""

import sys
import os
import glob
import importlib.util
from contextlib import contextmanager
from typing import Callable, Any


@contextmanager
def temporary_sys_path(paths: list[str]):
    """sys.path に一時的に複数のパスを追加するコンテキストマネージャ。"""
    added_paths = []
    for path in reversed(paths):
        abs_path = os.path.abspath(path)
        if abs_path not in sys.path:
            sys.path.insert(0, abs_path)
            added_paths.append(abs_path)
    try:
        yield
    finally:
        for path in added_paths:
            try:
                sys.path.remove(path)
            except ValueError:
                pass


def discover_agents(project_root: str) -> dict[str, str]:
    """リポジトリ内の有効なエージェントフォルダを検出する。

    有効なエージェントフォルダとは、直下に `main.py`、`deck.csv` が存在する
    `sample_submission` または `agents/` 配下のディレクトリです。

    Args:
        project_root: プロジェクトのルートディレクトリパス。

    Returns:
        dict[str, str]: エージェント名 (ディレクトリのベース名) から
                       そのエージェントの絶対パスへのマッピング。
    """
    agents = {}
    abs_root = os.path.abspath(project_root)

    # 1. sample_submission の確認
    sample_dir = os.path.join(abs_root, "sample_submission")
    if os.path.exists(os.path.join(sample_dir, "main.py")) and os.path.exists(
        os.path.join(sample_dir, "deck.csv")
    ):
        agents["sample_submission"] = sample_dir

    # 2. agents/ 配下の確認
    agents_parent = os.path.join(abs_root, "agents")
    if os.path.exists(agents_parent) and os.path.isdir(agents_parent):
        for item in os.listdir(agents_parent):
            item_path = os.path.join(agents_parent, item)
            if os.path.isdir(item_path):
                # 直下に main.py と deck.csv があるか確認
                if os.path.exists(
                    os.path.join(item_path, "main.py")
                ) and os.path.exists(os.path.join(item_path, "deck.csv")):
                    agents[item] = item_path

    return agents


def make_agent_wrapper(original_agent: Callable, agent_dir: str) -> Callable:
    """エージェント実行時に CWD と sys.path をそのエージェントのディレクトリに切り替えるラッパー。

    Args:
        original_agent: ロードされた元の agent 関数。
        agent_dir: そのエージェントが存在するディレクトリのパス。

    Returns:
        Callable: ラップされたエージェント関数。
    """

    def wrapper(obs_dict: dict) -> list[int]:
        original_cwd = os.getcwd()
        # カレントワーキングディレクトリを一時的に変更
        os.chdir(agent_dir)
        try:
            # sys.path にエージェントフォルダを追加して実行
            with temporary_sys_path([agent_dir]):
                return original_agent(obs_dict)
        finally:
            # 必ず元のディレクトリに戻す
            os.chdir(original_cwd)

    return wrapper


def load_agent(path: str) -> Callable:
    """指定されたパスの Python ファイルから agent 関数をロードし、ラッパーを適用して返す。

    Args:
        path: agent 関数を含む Python ファイル (例: main.py) へのパス。

    Returns:
        Callable: ロードされ、CWDスイッチが施された agent ラッパー関数。
    """
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Agent file not found: {abs_path}")

    # モジュール名が一意になるようにパスからハッシュ/IDを生成して命名
    module_name = f"agent_{os.path.basename(abs_path).replace('.', '_')}_{id(abs_path)}"

    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {abs_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    agent_dir = os.path.dirname(abs_path)

    # ロード自体も一時的にエージェントディレクトリおよび共通 sample_submission パスを sys.path に含めて実行
    project_root = os.path.abspath(os.path.join(agent_dir, "..", ".."))
    common_dir = os.path.join(project_root, "sample_submission")
    with temporary_sys_path([agent_dir, common_dir]):
        spec.loader.exec_module(module)

    if not hasattr(module, "agent"):
        raise AttributeError(f"Module at {abs_path} does not have an 'agent' function")

    original_agent = module.agent
    return make_agent_wrapper(original_agent, agent_dir)


def load_deck(agent_dir: str) -> list[int]:
    """エージェントフォルダの deck.csv からデッキデータをロードする。

    Args:
        agent_dir: エージェントが存在するディレクトリのパス。

    Returns:
        list[int]: 60枚のカードIDリスト。
    """
    deck_path = os.path.join(agent_dir, "deck.csv")
    if not os.path.exists(deck_path):
        raise FileNotFoundError(f"deck.csv not found at {deck_path}")

    with open(deck_path, "r") as f:
        deck = [int(line) for line in f.readlines() if line.strip()]
    return deck
