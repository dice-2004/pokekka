"""勝率測定ベンチマーク

指定された2つのエージェント、あるいは自動検出された全エージェント間での
対戦（総当たり戦、またはベースライン対戦）を行い、勝率を測定・集計するスクリプト。

使用例:
    # 1. 個別対戦 (エージェントA vs エージェントB)
    python tests/benchmark.py \
        --agent-a sample_submission/main.py \
        --agent-b agents/rules_baseline/main.py \
        --matches 20

    # 2. 総当たり戦 (リポジトリ内のすべてのエージェント間で総当たり戦)
    python tests/benchmark.py --round-robin --matches 10

    # 3. ベースライン対戦 (すべてのエージェント vs 標準サンプル)
    python tests/benchmark.py --baseline sample_submission/main.py --matches 20
"""

import sys
import os
import argparse
import itertools
from typing import Tuple

# プロジェクトルートを sys.path に追加して utils をロード
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tests.utils import discover_agents, load_agent, load_deck  # noqa: E402


def patch_kaggle_environments() -> None:
    """kaggle-environments 内の cabt ゲームエンジンを sample_submission/cg の最新版で上書きする。"""
    import importlib
    import importlib.util
    import shutil
    import filecmp

    spec = importlib.util.find_spec("kaggle_environments")
    if spec is None or spec.origin is None:
        return

    ke_path = os.path.dirname(spec.origin)
    target_cg_dir = os.path.join(ke_path, "envs", "cabt", "cg")

    if not os.path.exists(target_cg_dir):
        return

    source_cg_dir = os.path.join(project_root, "sample_submission", "cg")
    if not os.path.exists(source_cg_dir):
        return

    files_to_copy = [
        "libcg.so",
        "cg.dll",
        "game.py",
        "sim.py",
        "utils.py",
        "api.py",
        "__init__.py",
    ]
    patched = False

    for file_name in files_to_copy:
        src = os.path.join(source_cg_dir, file_name)
        dst = os.path.join(target_cg_dir, file_name)
        if os.path.exists(src):
            try:
                # Check if file differs to prevent redundant copies
                if not os.path.exists(dst) or not filecmp.cmp(src, dst, shallow=False):
                    shutil.copyfile(src, dst)
                    patched = True
            except Exception as e:
                print(f"Warning: Failed to copy {file_name} to {dst}: {e}")

    if patched:
        # Clear target __pycache__ to force recompilation
        pycache_dir = os.path.join(target_cg_dir, "__pycache__")
        if os.path.exists(pycache_dir):
            try:
                shutil.rmtree(pycache_dir)
            except Exception as e:
                print(f"Warning: Failed to remove __pycache__ at {pycache_dir}: {e}")
        importlib.invalidate_caches()
        print(
            "Successfully patched kaggle-environments with the latest cabt game engine."
        )


def run_match_series(
    agent_a_path: str,
    agent_b_path: str,
    matches: int,
    agent_a_name: str = "Agent A",
    agent_b_name: str = "Agent B",
) -> Tuple[int, int, int, int]:
    """2つのエージェントを指定された回数対戦させ、結果を集計して返す。

    Returns:
        Tuple[int, int, int, int]: (Aの勝利数, Bの勝利数, 引き分け数, エラー数)
    """
    from kaggle_environments import make

    try:
        # それぞれのエージェントをロード (ラッパー適用済み)
        agent_a = load_agent(agent_a_path)
        agent_b = load_agent(agent_b_path)

        # それぞれのデッキをロード
        deck_a = load_deck(os.path.dirname(agent_a_path))
        deck_b = load_deck(os.path.dirname(agent_b_path))
    except Exception as e:
        print(f"Error initializing agents for match: {e}")
        return 0, 0, 0, matches

    a_wins = 0
    b_wins = 0
    draws = 0
    errors = 0

    for i in range(matches):
        # 先攻・後攻を交互に入れ替え
        a_is_player0 = i % 2 == 0
        players = [agent_a, agent_b] if a_is_player0 else [agent_b, agent_a]
        match_decks = [deck_a, deck_b] if a_is_player0 else [deck_b, deck_a]

        try:
            env = make("cabt", configuration={"decks": match_decks}, debug=False)
            env.run(players)
        except Exception as e:
            print(f"Match {i + 1}: Error - {e}")
            errors += 1
            continue

        # エラー確認
        has_error = False
        for ps in env.state:
            if getattr(ps, "status", None) == "ERROR":
                has_error = True
                break
        if has_error:
            errors += 1
            print(f"Match {i + 1}: Agent error.")
            continue

        reward_0 = getattr(env.state[0], "reward", None)
        reward_1 = getattr(env.state[1], "reward", None)

        if reward_0 is None or reward_1 is None:
            errors += 1
            error_msg = (
                env.steps[0][0].get("error")
                if (hasattr(env, "steps") and env.steps)
                else "Unknown error"
            )
            print(f"Match {i + 1}: Game error. Details: {error_msg}")
            continue

        # 勝敗判定（先攻後攻の入れ替えを考慮）
        if reward_0 > reward_1:
            winner_is_player0 = True
        elif reward_1 > reward_0:
            winner_is_player0 = False
        else:
            draws += 1
            continue

        if a_is_player0:
            if winner_is_player0:
                a_wins += 1
            else:
                b_wins += 1
        else:
            if winner_is_player0:
                b_wins += 1
            else:
                a_wins += 1

    return a_wins, b_wins, draws, errors


def run_round_robin(matches_per_pair: int) -> None:
    """すべての自動検出されたエージェント間で総当たり戦を行う。"""
    agents = discover_agents(project_root)
    if len(agents) < 2:
        print("Error: Need at least 2 agents to run a round-robin tournament.")
        print(f"Discovered agents: {list(agents.keys())}")
        return

    print("\n" + "=" * 50)
    print(
        f" Starting Round-Robin Tournament ({len(agents)} agents, {matches_per_pair} matches/pair)"
    )
    print("=" * 50)
    print(f"Detected agents: {list(agents.keys())}")

    # 結果保存用スコアボード
    # {agent_name: {"wins": 0, "losses": 0, "draws": 0, "errors": 0, "points": 0}}
    scoreboard = {
        name: {"wins": 0, "losses": 0, "draws": 0, "errors": 0, "points": 0.0}
        for name in agents
    }

    pairs = list(itertools.combinations(agents.keys(), 2))

    for idx, (name_a, name_b) in enumerate(pairs):
        print(
            f"\n[{idx+1}/{len(pairs)}] Matchup: {name_a} vs {name_b} ({matches_per_pair} matches)"
        )
        path_a = os.path.join(agents[name_a], "main.py")
        path_b = os.path.join(agents[name_b], "main.py")

        a_wins, b_wins, draws, errors = run_match_series(
            path_a, path_b, matches_per_pair, name_a, name_b
        )

        print(
            f"  Result: {name_a} {a_wins} wins | {name_b} {b_wins} wins | Draws: {draws} | Errors: {errors}"
        )

        # スコアボード更新 (勝利=1点, 引き分け=0.5点)
        scoreboard[name_a]["wins"] += a_wins
        scoreboard[name_a]["losses"] += b_wins
        scoreboard[name_a]["draws"] += draws
        scoreboard[name_a]["errors"] += errors
        scoreboard[name_a]["points"] += a_wins + (draws * 0.5)

        scoreboard[name_b]["wins"] += b_wins
        scoreboard[name_b]["losses"] += a_wins
        scoreboard[name_b]["draws"] += draws
        scoreboard[name_b]["errors"] += errors
        scoreboard[name_b]["points"] += b_wins + (draws * 0.5)

    # 勝点でソートして順位表を出力
    sorted_scoreboard = sorted(
        scoreboard.items(), key=lambda x: x[1]["points"], reverse=True
    )

    print("\n" + "=" * 60)
    print(" Tournament Standings")
    print("=" * 60)
    print(
        f"{'Rank':<5} | {'Agent':<25} | {'Points':<8} | {'W-L-D':<10} | {'Errors':<6}"
    )
    print("-" * 60)
    for rank, (name, stats) in enumerate(sorted_scoreboard, 1):
        wld = f"{stats['wins']}-{stats['losses']}-{stats['draws']}"
        print(
            f"{rank:<5} | {name:<25} | {stats['points']:<8.1f} | {wld:<10} | {stats['errors']:<6}"
        )
    print("=" * 60)


def run_baseline_mode(baseline_path: str, matches_per_pair: int) -> None:
    """指定されたベースラインエージェントと、それ以外のすべてのアクティブなエージェントを対戦させる。"""
    abs_baseline_path = os.path.abspath(baseline_path)
    if not os.path.exists(abs_baseline_path):
        print(f"Error: Baseline agent not found at {abs_baseline_path}")
        return

    baseline_dir = os.path.dirname(abs_baseline_path)
    baseline_name = os.path.basename(baseline_dir)
    if baseline_name == "sample_submission" or not baseline_name:
        baseline_name = "baseline"

    agents = discover_agents(project_root)

    print("\n" + "=" * 50)
    print(
        f" Starting Baseline Matchups (Vs: {baseline_name}, {matches_per_pair} matches each)"
    )
    print("=" * 50)

    results = []

    for name, path in agents.items():
        # 同一フォルダはスキップ
        agent_main = os.path.join(path, "main.py")
        if os.path.abspath(agent_main) == abs_baseline_path:
            continue

        print(f"\nMatchup: {name} vs {baseline_name}...")
        a_wins, b_wins, draws, errors = run_match_series(
            agent_main, abs_baseline_path, matches_per_pair, name, baseline_name
        )

        total_completed = a_wins + b_wins + draws
        win_rate = (a_wins / total_completed * 100) if total_completed > 0 else 0
        print(
            f"  Result: {name} {a_wins} wins ({win_rate:.1f}%) | "
            f"{baseline_name} {b_wins} wins | Draws: {draws} | Errors: {errors}"
        )

        results.append(
            {
                "agent": name,
                "wins": a_wins,
                "losses": b_wins,
                "draws": draws,
                "errors": errors,
                "win_rate": win_rate,
            }
        )

    print("\n" + "=" * 65)
    print(f" Benchmark Summary (Vs: {baseline_name})")
    print("=" * 65)
    print(
        f"{'Agent':<25} | {'Win Rate':<10} | {'Wins':<6} | {'Losses':<6} | {'Draws':<6} | {'Errors':<6}"
    )
    print("-" * 65)
    for res in results:
        print(
            f"{res['agent']:<25} | {res['win_rate']:>8.1f}% | "
            f"{res['wins']:<6} | {res['losses']:<6} | {res['draws']:<6} | {res['errors']:<6}"
        )
    print("=" * 65)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Pokémon TCG agents.")
    parser.add_argument("--agent-a", help="Path to agent A python file (e.g. main.py)")
    parser.add_argument("--agent-b", help="Path to agent B python file (e.g. main.py)")
    parser.add_argument(
        "--matches",
        type=int,
        default=50,
        help="Number of matches to play (even number recommended)",
    )
    parser.add_argument(
        "--round-robin",
        action="store_true",
        help="Run a round-robin tournament among all discovered agents",
    )
    parser.add_argument(
        "--baseline",
        help="Path to a baseline agent main.py to compare all others against",
    )
    args = parser.parse_args()

    # Automatically patch kaggle-environments with the local simulation engine
    patch_kaggle_environments()

    try:
        from kaggle_environments import make
    except ImportError:
        print("Error: kaggle-environments is not installed.")
        print("Please run: pip install kaggle-environments")
        sys.exit(1)

    # Force load the cabt environment to initialize its modules
    try:
        make("cabt")
    except Exception:
        pass

    # Alias cg modules to prevent double-loading libcg.so when agents import cg
    for module_name in list(sys.modules.keys()):
        if module_name.startswith("kaggle_environments.envs.cabt.cg"):
            suffix = module_name[
                len("kaggle_environments.envs.cabt.cg") :
            ]  # noqa: E203
            alias_name = "cg" + suffix
            sys.modules[alias_name] = sys.modules[module_name]

    # Set PTCG_PROJECT_ROOT to the repository root
    os.environ["PTCG_PROJECT_ROOT"] = project_root

    # モードの判定と実行
    if args.round_robin:
        run_round_robin(args.matches)
    elif args.baseline:
        run_baseline_mode(args.baseline, args.matches)
    elif args.agent_a and args.agent_b:
        # 個別対戦
        print(f"Starting benchmark: {args.matches} matches...")
        print(f"Agent A: {args.agent_a}")
        print(f"Agent B: {args.agent_b}")

        a_wins, b_wins, draws, errors = run_match_series(
            args.agent_a, args.agent_b, args.matches
        )

        total_played = a_wins + b_wins + draws
        a_win_rate = (a_wins / total_played * 100) if total_played > 0 else 0
        b_win_rate = (b_wins / total_played * 100) if total_played > 0 else 0

        print("\n" + "=" * 50)
        print(" Benchmark Results")
        print("=" * 50)
        print(f"Total Matches:     {args.matches}")
        print(f"Completed Matches: {total_played}")
        print(f"Errors/Crashes:    {errors}")
        print(f"Agent A Wins:      {a_wins} ({a_win_rate:.1f}%)")
        print(f"Agent B Wins:      {b_wins} ({b_win_rate:.1f}%)")
        print(f"Draws:             {draws}")
        print("=" * 50)
        print(f"SUMMARY: A_WIN_RATE={a_win_rate:.2f} B_WIN_RATE={b_win_rate:.2f}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
