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
from typing import Tuple, List, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

try:
    from tqdm import tqdm
except ImportError:
    # tqdm がない場合はフォールバック
    def tqdm(iterable, *args, **kwargs):
        return iterable


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


def run_single_match_worker(
    args_tuple: Tuple[str, str, int, bool],
) -> Tuple[int, Dict[str, Any]]:
    """ワーカープロセス内で実行される、1ゲームの対戦シミュレーション。

    C++ ライブラリ libcg.so の状態干渉とメモリリークを防ぐため、
    プロセスレベルで完全に隔離された空間で実行します。
    """
    agent_a_path, agent_b_path, match_id, is_player0_a = args_tuple

    # 子プロセス環境の初期化
    os.environ["PTCG_PROJECT_ROOT"] = project_root

    # kaggle-environments の事前ロード
    from kaggle_environments import make

    try:
        make("cabt")
    except Exception:
        pass

    # cg モジュールのエイリアスを設定し、二重ロードを防止
    import sys

    for module_name in list(sys.modules.keys()):
        if module_name.startswith("kaggle_environments.envs.cabt.cg"):
            suffix = module_name[len("kaggle_environments.envs.cabt.cg") :]
            alias_name = "cg" + suffix
            sys.modules[alias_name] = sys.modules[module_name]

    try:
        # エージェント関数とデッキをロード
        agent_a = load_agent(agent_a_path)
        agent_b = load_agent(agent_b_path)
        deck_a = load_deck(os.path.dirname(agent_a_path))
        deck_b = load_deck(os.path.dirname(agent_b_path))
    except Exception as e:
        return match_id, {"winner": -2, "error": f"Initialization failed: {e}"}

    # 先攻・後攻の入れ替え
    players = [agent_a, agent_b] if is_player0_a else [agent_b, agent_a]
    match_decks = [deck_a, deck_b] if is_player0_a else [deck_b, deck_a]

    try:
        env = make("cabt", configuration={"decks": match_decks}, debug=False)
        env.run(players)
    except Exception as e:
        return match_id, {"winner": -2, "error": f"Execution crashed: {e}"}

    # 対戦中にエラーが発生したか確認
    has_error = False
    for ps in env.state:
        if getattr(ps, "status", None) == "ERROR":
            has_error = True
            break
    if has_error:
        return match_id, {"winner": -2, "error": "Agent execution error."}

    reward_0 = getattr(env.state[0], "reward", None)
    reward_1 = getattr(env.state[1], "reward", None)

    if reward_0 is None or reward_1 is None:
        return match_id, {"winner": -2, "error": "No reward data computed."}

    # 勝者判定（先攻・後攻の入れ替えを考慮）
    if reward_0 > reward_1:
        winner_is_player0 = True
    elif reward_1 > reward_0:
        winner_is_player0 = False
    else:
        # 引き分け
        return match_id, {"winner": -1, "error": None}

    if is_player0_a:
        winner = 0 if winner_is_player0 else 1
    else:
        winner = 1 if winner_is_player0 else 0

    return match_id, {"winner": winner, "error": None}


def run_match_series(
    agent_a_path: str,
    agent_b_path: str,
    matches: int,
    agent_a_name: str = "Agent A",
    agent_b_name: str = "Agent B",
    workers: int = 1,
) -> Tuple[int, int, int, int]:
    """2つのエージェントを指定された回数対戦させ、結果を集計して返す。

    Args:
        agent_a_path: エージェントAの Python ファイルパス。
        agent_b_path: エージェントBの Python ファイルパス。
        matches: 対戦数。
        agent_a_name: エージェントAの表示用名前。
        agent_b_name: エージェントBの表示用名前。
        workers: 並列実行するワーカー数。1 の場合はシングルプロセス（同期）実行。

    Returns:
        Tuple[int, int, int, int]: (Aの勝利数, Bの勝利数, 引き分け数, エラー数)
    """
    a_wins = 0
    b_wins = 0
    draws = 0
    errors = 0

    # タスク引数の作成 (Aが先攻かどうかを交互に変更)
    tasks = [(agent_a_path, agent_b_path, i, i % 2 == 0) for i in range(matches)]

    # 1. マルチプロセス並列実行
    if workers > 1:
        print(f"Running matches in parallel using {workers} worker processes...")
        # tqdm の進捗バー付きで実行
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_single_match_worker, task) for task in tasks]
            for future in tqdm(as_completed(futures), total=matches, desc="Simulating"):
                try:
                    _, result = future.result()
                    winner = result["winner"]
                    if winner == 0:
                        a_wins += 1
                    elif winner == 1:
                        b_wins += 1
                    elif winner == -1:
                        draws += 1
                    else:
                        errors += 1
                        if result["error"]:
                            print(f"  Game error: {result['error']}")
                except Exception as e:
                    errors += 1
                    print(f"  Future resolution error: {e}")

    # 2. シングルプロセス（同期）実行
    else:
        # デバッグや1コア実行時は従来通り同期で実行
        for i, task in enumerate(tqdm(tasks, desc="Simulating")):
            _, result = run_single_match_worker(task)
            winner = result["winner"]
            if winner == 0:
                a_wins += 1
            elif winner == 1:
                b_wins += 1
            elif winner == -1:
                draws += 1
            else:
                errors += 1
                if result["error"]:
                    print(f"Match {i + 1}: {result['error']}")

    return a_wins, b_wins, draws, errors


def run_round_robin(matches_per_pair: int, workers: int = 1) -> None:
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
            path_a, path_b, matches_per_pair, name_a, name_b, workers=workers
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


def run_baseline_mode(
    baseline_path: str, matches_per_pair: int, workers: int = 1
) -> None:
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
            agent_main,
            abs_baseline_path,
            matches_per_pair,
            name,
            baseline_name,
            workers=workers,
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
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="Number of parallel worker processes. Set to 1 for sequential execution.",
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
        run_round_robin(args.matches, workers=args.workers)
    elif args.baseline:
        run_baseline_mode(args.baseline, args.matches, workers=args.workers)
    elif args.agent_a and args.agent_b:
        # 個別対戦
        print(f"Starting benchmark: {args.matches} matches...")
        print(f"Agent A: {args.agent_a}")
        print(f"Agent B: {args.agent_b}")

        a_wins, b_wins, draws, errors = run_match_series(
            args.agent_a, args.agent_b, args.matches, workers=args.workers
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
