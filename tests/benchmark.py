"""勝率測定ベンチマーク

2つのエージェントを指定回数対戦させ、勝率を測定・集計するスクリプト。
先攻・後攻を交互に入れ替えて公平性を担保する。

使用例:
    python tests/benchmark.py \
        --agent-a sample_submission/main.py \
        --agent-b sample_submission/main_base.py \
        --matches 50
"""

import sys
import os
import argparse
import importlib.util
from contextlib import contextmanager
from typing import Callable


@contextmanager
def temporary_sys_path(path: str):
    """sys.path に一時的にパスを追加するコンテキストマネージャ。"""
    sys.path.insert(0, path)
    try:
        yield
    finally:
        try:
            sys.path.remove(path)
        except ValueError:
            pass


def patch_kaggle_environments() -> None:
    """kaggle-environments 内の cabt ゲームエンジンを sample_submission/cg の最新版で上書きする。"""
    import importlib
    import importlib.util
    import shutil

    spec = importlib.util.find_spec("kaggle_environments")
    if spec is None or spec.origin is None:
        return

    ke_path = os.path.dirname(spec.origin)
    target_cg_dir = os.path.join(ke_path, "envs", "cabt", "cg")

    if not os.path.exists(target_cg_dir):
        return

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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
                # size or modification time check
                if not os.path.exists(dst) or os.path.getsize(src) != os.path.getsize(
                    dst
                ):
                    shutil.copyfile(src, dst)
                    os.utime(dst, None)  # Force update timestamp to now
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


def load_agent(path: str) -> Callable:
    """指定されたパスの Python ファイルから agent 関数をロードする。

    Args:
        path: agent 関数を含む Python ファイルへのパス。

    Returns:
        ロードされた agent 関数。

    Raises:
        FileNotFoundError: ファイルが見つからない場合。
        ImportError: モジュールのロードに失敗した場合。
        AttributeError: agent 関数がモジュールに存在しない場合。
    """
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Agent file not found: {abs_path}")

    module_name = f"agent_{os.path.basename(abs_path).replace('.', '_')}_{id(abs_path)}"

    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {abs_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    parent_dir = os.path.dirname(abs_path)
    with temporary_sys_path(parent_dir):
        spec.loader.exec_module(module)

    if not hasattr(module, "agent"):
        raise AttributeError(f"Module at {abs_path} does not have an 'agent' function")

    return module.agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark two Pokémon TCG agents.")
    parser.add_argument("--agent-a", required=True, help="Path to agent A python file")
    parser.add_argument("--agent-b", required=True, help="Path to agent B python file")
    parser.add_argument(
        "--matches",
        type=int,
        default=50,
        help="Number of matches to play (even number recommended)",
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
            suffix = module_name[len("kaggle_environments.envs.cabt.cg") :]
            alias_name = "cg" + suffix
            sys.modules[alias_name] = sys.modules[module_name]

    # デッキのロード
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.environ["PTCG_PROJECT_ROOT"] = project_root
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    deck_path = os.path.join(project_root, "sample_submission", "deck.csv")
    if not os.path.exists(deck_path):
        print(f"Error: deck.csv not found at {deck_path}")
        sys.exit(1)

    with open(deck_path) as f:
        deck = [int(line) for line in f.readlines() if line.strip()]

    # Copy deck.csv temporarily to CWD to let unmodified agents load it successfully
    temp_deck_path = os.path.join(project_root, "deck.csv")
    temp_copied = False
    if not os.path.exists(temp_deck_path):
        import shutil

        shutil.copy2(deck_path, temp_deck_path)
        temp_copied = True

    try:
        try:
            agent_a = load_agent(args.agent_a)
            agent_b = load_agent(args.agent_b)
        except Exception as e:
            print(f"Error loading agents: {e}")
            sys.exit(1)

        print(f"Starting benchmark: {args.matches} matches...")
        print(f"Agent A: {args.agent_a}")
        print(f"Agent B: {args.agent_b}")

        a_wins = 0
        b_wins = 0
        draws = 0
        errors = 0

        for i in range(args.matches):
            # 先攻・後攻を交互に入れ替え
            a_is_player0 = i % 2 == 0
            players = [agent_a, agent_b] if a_is_player0 else [agent_b, agent_a]

            try:
                env = make("cabt", configuration={"decks": [deck, deck]}, debug=False)
                env.run(players)
            except Exception as e:
                print(f"Match {i + 1}: Error - {e}")
                errors += 1
                continue

            # エラー確認（属性アクセスに統一）
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

        total_played = args.matches - errors
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

    finally:
        if temp_copied and os.path.exists(temp_deck_path):
            try:
                os.remove(temp_deck_path)
            except Exception as e:
                print(f"Warning: Failed to remove temporary deck.csv: {e}")


if __name__ == "__main__":
    main()
