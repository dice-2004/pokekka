"""テストおよびベンチマーク用共通ユーティリティ"""

import sys
import os
import importlib.util
from contextlib import contextmanager
from typing import Callable


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


def _is_valid_agent_dir(path: str) -> bool:
    """ディレクトリが有効なエージェントフォルダかを判定する。

    有効条件: 直下に ``main.py`` と ``deck.csv`` が存在すること。
    """
    return (
        os.path.isdir(path)
        and os.path.isfile(os.path.join(path, "main.py"))
        and os.path.isfile(os.path.join(path, "deck.csv"))
    )


def _scan_agent_subfolders(
    parent_dir: str,
    key_prefix: str,
) -> dict[str, str]:
    """親ディレクトリ直下のサブフォルダから有効なエージェントを収集する。

    Args:
        parent_dir: 走査対象の親ディレクトリ (例: ``agents_draft/``)。
        key_prefix: 返却辞書のキーに付与するプレフィックス
                    (例: ``"draft"`` → ``"draft/{name}"``)。

    Returns:
        dict[str, str]: ``"{prefix}/{name}"`` → 絶対パスのマッピング。
    """
    results: dict[str, str] = {}
    if not os.path.isdir(parent_dir):
        return results

    for item in sorted(os.listdir(parent_dir)):
        item_path = os.path.join(parent_dir, item)
        if _is_valid_agent_dir(item_path):
            results[f"{key_prefix}/{item}"] = item_path
    return results


def discover_agents(
    project_root: str,
    *,
    include_draft: bool = True,
    include_completed: bool = True,
    include_submission: bool = True,
    include_sample: bool = False,
) -> dict[str, str]:
    """リポジトリ内の有効なエージェントフォルダを検出する。

    3層エージェントディレクトリ構造に対応しています。

    - ``agents_draft/``    — 作業中エージェント (キー: ``draft/{name}``)
    - ``agents/``          — 完成済みエージェント (キー: ``completed/{name}``)
    - ``latest_submission/`` — 提出予定エージェント (キー: ``latest_submission``)
    - ``sample_submission/`` — テンプレート (キー: ``sample_submission``)

    各カテゴリの検出はフラグで個別に制御できます。

    Args:
        project_root: プロジェクトのルートディレクトリパス。
        include_draft: ``agents_draft/`` を検出対象に含める。
        include_completed: ``agents/`` を検出対象に含める。
        include_submission: ``latest_submission/`` を検出対象に含める。
        include_sample: ``sample_submission/`` を検出対象に含める。

    Returns:
        dict[str, str]: エージェント識別名からそのエージェントの
                       絶対パスへのマッピング。
    """
    agents: dict[str, str] = {}
    abs_root = os.path.abspath(project_root)

    # 1. agents_draft/ 配下 (作業中)
    if include_draft:
        draft_dir = os.path.join(abs_root, "agents_draft")
        agents.update(_scan_agent_subfolders(draft_dir, "draft"))

    # 2. agents/ 配下 (完成済み)
    if include_completed:
        completed_dir = os.path.join(abs_root, "agents")
        agents.update(_scan_agent_subfolders(completed_dir, "completed"))

    # 3. latest_submission/ (提出予定)
    if include_submission:
        submission_dir = os.path.join(abs_root, "latest_submission")
        if _is_valid_agent_dir(submission_dir):
            agents["latest_submission"] = submission_dir

    # 4. sample_submission/ (テンプレート)
    if include_sample:
        sample_dir = os.path.join(abs_root, "sample_submission")
        if _is_valid_agent_dir(sample_dir):
            agents["sample_submission"] = sample_dir

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
