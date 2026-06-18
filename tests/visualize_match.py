"""対戦ビジュアル出力スクリプト

2つのエージェントを対戦させ、対戦のビジュアルビューア（HTML）を出力する。
ブラウザで出力された HTML を開くことで対戦経過を可視化して確認できる。

使用例:
    python tests/visualize_match.py \
        --agent-a sample_submission/main.py \
        --agent-b sample_submission/main.py \
        --output scratch/visualizer.html
"""

import sys
import os
import argparse

# tests/ ディレクトリを sys.path に追加して benchmark からモジュールをインポート可能にする
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from benchmark import load_agent, patch_kaggle_environments


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one match and generate an HTML visualizer."
    )
    parser.add_argument("--agent-a", required=True, help="Path to agent A python file")
    parser.add_argument("--agent-b", required=True, help="Path to agent B python file")
    parser.add_argument(
        "--output", default="scratch/visualizer.html", help="Path to output HTML file"
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
    temp_deck_path = os.path.join(os.getcwd(), "deck.csv")
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

        print(f"Running match...")
        print(f"Agent A: {args.agent_a}")
        print(f"Agent B: {args.agent_b}")

        env = make("cabt", configuration={"decks": [deck, deck]}, debug=True)
        env.run([agent_a, agent_b])

        # Output dir check
        output_dir = os.path.dirname(os.path.abspath(args.output))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        print(f"Rendering match results to {args.output}...")
        html_content = env.render(mode="html")
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html_content)

        print("Done. Please open the HTML file in a web browser to view the match.")

    finally:
        if temp_copied and os.path.exists(temp_deck_path):
            try:
                os.remove(temp_deck_path)
            except Exception as e:
                print(f"Warning: Failed to remove temporary deck.csv: {e}")


if __name__ == "__main__":
    main()
