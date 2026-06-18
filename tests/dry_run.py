"""動作検証テスト (Dry Run)

エージェントがシミュレータ環境で正常に1ゲーム完了できるかを検証するスクリプト。
引数なしで実行された場合はリポジトリ内のすべてのエージェントを自動検出し、
それぞれのフォルダ内の `deck.csv` とエージェントコードを用いて動作検証を順次行います。

使用例:
    # すべてのエージェントを一括テスト
    python tests/dry_run.py

    # 特定のエージェントを指定してテスト
    python tests/dry_run.py --agent-dir agents/rules_baseline
"""

import sys
import os
import argparse
import traceback

# プロジェクトルートを sys.path に追加して utils をロード
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tests.utils import (
    discover_agents,
    load_agent,
    load_deck,
    temporary_sys_path,
)  # noqa: E402


def run_dry_test(agent_name: str, agent_dir: str) -> bool:
    """指定されたエージェントの動作検証（Dry Run）を行う。"""
    print("\n" + "=" * 50)
    print(f" Testing Agent: {agent_name}")
    print(f" Path: {agent_dir}")
    print("=" * 50)

    # デッキのロード
    try:
        deck = load_deck(agent_dir)
        print(f"Deck loaded: {len(deck)} cards")
    except Exception as e:
        print(f"Error loading deck: {e}")
        return False

    # Set PTCG_PROJECT_ROOT for GameInitialize to locate CSVs
    os.environ["PTCG_PROJECT_ROOT"] = project_root

    # エージェント関数のロード (ラッパー付き)
    agent_main_py = os.path.join(agent_dir, "main.py")
    try:
        agent_fn = load_agent(agent_main_py)
    except Exception as e:
        print(f"Error loading agent code: {e}")
        traceback.print_exc()
        return False

    # エージェントのディレクトリ内の cg モジュールをインポートしてテストを行う
    original_cwd = os.getcwd()
    os.chdir(agent_dir)

    try:
        # sys.path にエージェントフォルダを追加して、そのフォルダ内の cg をロードする
        with temporary_sys_path([agent_dir]):
            from cg.game import battle_start, battle_select, battle_finish
            from cg.api import to_observation_class

            print("Starting battle simulation...")
            obs_dict, start_data = battle_start(deck, deck)
            if obs_dict is None:
                print(
                    f"Battle start failed. "
                    f"errorPlayer={start_data.errorPlayer}, "
                    f"errorType={start_data.errorType}"
                )
                return False

            print("Battle started successfully. Stepping...")

            step = 0
            max_steps = 5000  # 無限ループ防止

            while step < max_steps:
                obs = to_observation_class(obs_dict)

                # 試合終了判定
                if obs.current is not None and obs.current.result != -1:
                    print(f"Game ended at step {step}. Result: {obs.current.result}")
                    break

                # エージェントに選択させる
                action = agent_fn(obs_dict)
                obs_dict = battle_select(action)
                step += 1
            else:
                print(f"Warning: Reached max_steps ({max_steps}) without game ending.")
                return False

    except Exception as e:
        current_step = locals().get("step", 0)
        print(f"Error at step {current_step}: {e}")
        traceback.print_exc()
        return False
    finally:
        try:
            from cg.game import battle_finish

            battle_finish()
        except Exception:
            pass
        os.chdir(original_cwd)

    print(f"Dry run completed successfully for {agent_name}. ({step} steps)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry run Pokémon TCG agents.")
    parser.add_argument(
        "--agent-dir",
        help="Path to specific agent directory (e.g. agents_draft/my_agent)",
    )
    parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed agents in agents/ directory during automatic discovery.",
    )
    args = parser.parse_args()

    if args.agent_dir:
        # 特定エージェントの検証
        agent_dir = os.path.abspath(args.agent_dir)
        if not os.path.exists(agent_dir) or not os.path.isdir(agent_dir):
            print(f"Error: Directory not found: {agent_dir}")
            sys.exit(1)
        agent_name = os.path.basename(agent_dir.rstrip("/"))
        success = run_dry_test(agent_name, agent_dir)
        sys.exit(0 if success else 1)
    else:
        # すべてのエージェントを自動検出して一括検証
        agents = discover_agents(
            project_root,
            include_completed=args.include_completed,
        )
        if not agents:
            print("No active agents found in agents/ or sample_submission/.")
            sys.exit(1)

        print(f"Discovered {len(agents)} agents to test: {list(agents.keys())}")
        failed_agents = []

        for name, path in agents.items():
            success = run_dry_test(name, path)
            if not success:
                failed_agents.append(name)

        print("\n" + "=" * 50)
        print(" Dry Run Summary")
        print("=" * 50)
        print(f"Total Tested: {len(agents)}")
        print(f"Passed:       {len(agents) - len(failed_agents)}")
        print(f"Failed:       {len(failed_agents)}")
        if failed_agents:
            print(f"Failed list:  {failed_agents}")
        print("=" * 50)

        sys.exit(1 if failed_agents else 0)


if __name__ == "__main__":
    main()
