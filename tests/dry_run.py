"""動作検証テスト (Dry Run)

エージェントがシミュレータ環境で正常に1ゲーム完了できるかを検証するスクリプト。
プロジェクトルートから `python tests/dry_run.py` で実行する。

cg.game モジュールを直接使用してシミュレーションを実行する。
kaggle-environments の cabt 環境はバージョン差異の影響を受ける可能性があるため、
ローカルテストではコンペ提供の cg モジュールを直接利用する。
"""

import sys
import os

# sample_submission/ を sys.path に追加
# main.py 内の `from cg.api import ...` が cg パッケージを見つけられるようにする
_SAMPLE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "sample_submission")
)
if _SAMPLE_DIR not in sys.path:
    sys.path.insert(0, _SAMPLE_DIR)

# Set PTCG_PROJECT_ROOT for GameInitialize to locate CSVs
os.environ["PTCG_PROJECT_ROOT"] = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# deck.csv の読み取りのため、CWD を sample_submission/ に変更
_ORIGINAL_CWD = os.getcwd()
os.chdir(_SAMPLE_DIR)


def main() -> None:
    from main import agent
    from cg.game import battle_start, battle_select, battle_finish
    from cg.api import to_observation_class

    # デッキのロード
    deck_path = os.path.join(_SAMPLE_DIR, "deck.csv")
    if not os.path.exists(deck_path):
        print(f"Error: deck.csv not found at {deck_path}")
        sys.exit(1)

    with open(deck_path) as f:
        deck = [int(line) for line in f.readlines() if line.strip()]

    print(f"Deck loaded: {len(deck)} cards")

    # cg.game で直接対戦を開始
    print("Starting battle...")
    obs_dict, start_data = battle_start(deck, deck)
    if obs_dict is None:
        print(
            f"Battle start failed. "
            f"errorPlayer={start_data.errorPlayer}, "
            f"errorType={start_data.errorType}"
        )
        sys.exit(1)

    print("Battle started successfully.")

    step = 0
    max_steps = 5000  # 無限ループ防止

    try:
        while step < max_steps:
            obs = to_observation_class(obs_dict)

            # 試合終了判定
            if obs.current is not None and obs.current.result != -1:
                print(f"Game ended at step {step}. Result: {obs.current.result}")
                break

            # エージェントに選択させる
            action = agent(obs_dict)
            obs_dict = battle_select(action)
            step += 1
        else:
            print(f"Warning: Reached max_steps ({max_steps}) without game ending.")
            sys.exit(1)
    except Exception as e:
        print(f"Error at step {step}: {e}")
        sys.exit(1)
    finally:
        battle_finish()
        os.chdir(_ORIGINAL_CWD)

    print(f"Dry run completed successfully. ({step} steps)")


if __name__ == "__main__":
    main()
