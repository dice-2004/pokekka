"""対戦ビジュアル出力スクリプト

指定された数の対戦を実行し、それぞれの試合の HEROZ社ビジュアル可視化サイトへ
POST遷移可能なリンクを一覧化したダッシュボード（HTML）を1つ生成する。
"""

import sys
import os
import argparse
import multiprocessing
import json

# プロジェクトルートを sys.path に追加して utils をロード
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tests.utils import load_agent, load_deck  # noqa: E402
from tests.benchmark import patch_kaggle_environments  # noqa: E402


def run_and_save_match(
    agent_a_path: str,
    agent_b_path: str,
    output_json_path: str,
    is_player0_a: bool,
    match_idx: int,
) -> None:
    """1ゲームの対戦シミュレーションを実行し、結果を JSON ファイルに保存する子プロセス関数。"""
    try:
        from kaggle_environments import make
    except ImportError:
        print("Error: kaggle-environments is not installed.")
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

    try:
        # エージェント関数のロード (ラッパー適用済み)
        agent_a = load_agent(agent_a_path)
        agent_b = load_agent(agent_b_path)

        # それぞれのデッキをロード
        deck_a = load_deck(os.path.dirname(agent_a_path))
        deck_b = load_deck(os.path.dirname(agent_b_path))

        # 先攻・後攻の入れ替え
        players = [agent_a, agent_b] if is_player0_a else [agent_b, agent_a]
        match_decks = [deck_a, deck_b] if is_player0_a else [deck_b, deck_a]

        env = make("cabt", configuration={"decks": match_decks}, debug=True)
        env.run(players)

        # 勝敗判定
        reward_0 = getattr(env.state[0], "reward", None)
        reward_1 = getattr(env.state[1], "reward", None)

        winner = -2  # Default to error
        error_msg = None

        # 対戦中にエラーが発生したか確認
        has_error = False
        for ps in env.state:
            if getattr(ps, "status", None) == "ERROR":
                has_error = True
                error_msg = getattr(ps, "message", "Agent execution error.")
                break

        if not has_error:
            if reward_0 is not None and reward_1 is not None:
                if reward_0 > reward_1:
                    winner_is_player0 = True
                elif reward_1 > reward_0:
                    winner_is_player0 = False
                else:
                    winner_is_player0 = None  # Draw

                if winner_is_player0 is None:
                    winner = -1
                elif is_player0_a:
                    winner = 0 if winner_is_player0 else 1
                else:
                    winner = 1 if winner_is_player0 else 0
            else:
                error_msg = "No reward data computed."

        # visualize リストの取得
        vis_list = None
        if env.steps and len(env.steps) > 0 and len(env.steps[0]) > 0:
            # Struct クラスは後から dict キーとして追加された要素への属性アクセス（.visualize）をサポートしないため、
            # get() メソッドを使用して安全に取得します。
            vis_list = env.steps[0][0].get("visualize")

            # vis_list 内の ramainingTime を steps から設定（cabt.js の挙動を模倣）
            if vis_list:
                for i in range(len(vis_list)):
                    for j in range(2):
                        step_row = env.steps[i]
                        player_step = (
                            step_row[j] if step_row and j < len(step_row) else None
                        )
                        obs = player_step.get("observation") if player_step else None
                        vis_list[i]["current"]["players"][j]["ramainingTime"] = (
                            obs.get("remainingOverageTime", 600) if obs else 600
                        )

                # プレイヤー名リストを vis_list[0]["ps"] に追加（cabt.js の挙動を模倣）
                if len(vis_list) > 0:
                    agent_a_name = os.path.basename(os.path.dirname(agent_a_path))
                    agent_b_name = os.path.basename(os.path.dirname(agent_b_path))
                    p0_name = agent_a_name if is_player0_a else agent_b_name
                    p1_name = agent_b_name if is_player0_a else agent_a_name
                    vis_list[0]["ps"] = [p0_name, p1_name]

        # info 取得
        info = getattr(env, "info", {})
        episode_id = info.get("EpisodeId", None) if info else None

        result_data = {
            "match_idx": match_idx,
            "is_player0_a": is_player0_a,
            "winner": winner,
            "turns": len(env.steps),
            "error": error_msg,
            "vis_list": vis_list,
            "episode_id": episode_id,
        }

        # JSONファイルとして出力
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f)

    except Exception as e:
        print(f"Error in match subprocess: {e}")
        sys.exit(1)


def generate_dashboard_html(
    agent_a: str,
    agent_b: str,
    matches_data: list,
    a_wins: int,
    b_wins: int,
    draws: int,
    errors: int,
) -> str:
    """対戦結果の一覧を表示するダッシュボード HTML を生成する。"""
    total = len(matches_data)
    win_rate_a = (a_wins / (total - errors) * 100) if (total - errors) > 0 else 0

    # E501 回避のため、事前にデータをJSONダンプしておく
    match_data_json = json.dumps(
        [
            {
                "match_idx": m["match_idx"],
                "episode_id": m["episode_id"],
                "vis_list": m["vis_list"],
            }
            for m in matches_data
        ]
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PTCG Battle Challenge Dashboard</title>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 29, 49, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --accent-a: #10b981; /* Green */
            --accent-b: #8b5cf6; /* Purple */
            --draw-color: #f59e0b; /* Yellow */
            --error-color: #ef4444; /* Red */
            --button-grad: linear-gradient(135deg, #4f46e5, #3b82f6);
            --button-grad-hover: linear-gradient(135deg, #4338ca, #2563eb);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: 'Outfit', 'Inter',
                -apple-system, BlinkMacSystemFont, sans-serif;
            min-height: 100vh;
            padding: 2rem 1rem;
        }}

        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            margin-bottom: 2.5rem;
        }}

        h1 {{
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(to right, #a5b4fc, #818cf8, #6366f1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 1.5rem;
        }}

        /* Summary Dashboard */
        .summary-dashboard {{
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem 2rem;
            display: grid;
            grid-template-columns: 1fr 1.2fr 1fr;
            align-items: center;
            gap: 1.5rem;
            margin-bottom: 2.5rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
        }}

        .summary-agent-a, .summary-agent-b {{
            text-align: center;
        }}

        .agent-name {{
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}

        .summary-agent-a .agent-name {{ color: var(--accent-a); }}
        .summary-agent-b .agent-name {{ color: var(--accent-b); }}

        .score {{
            font-size: 2.5rem;
            font-weight: 800;
        }}

        .summary-stats {{
            text-align: center;
            border-left: 1px solid var(--border-color);
            border-right: 1px solid var(--border-color);
            padding: 0 1.5rem;
        }}

        .win-rate {{
            font-size: 1.8rem;
            font-weight: 700;
            color: #f1f5f9;
            margin-bottom: 0.3rem;
        }}

        .win-rate span {{
            font-size: 0.9rem;
            color: var(--text-muted);
            font-weight: normal;
        }}

        .details-count {{
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        /* Match Cards */
        .match-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 1.5rem;
        }}

        .match-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }}

        .match-card:hover {{
            transform: translateY(-4px);
            border-color: rgba(255,255,255,0.15);
            box-shadow: 0 8px 25px rgba(0,0,0,0.25);
        }}

        .match-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.5rem;
        }}

        .match-title {{
            font-size: 1.1rem;
            font-weight: 700;
            color: #f1f5f9;
        }}

        .turns-badge {{
            background: rgba(255,255,255,0.06);
            padding: 0.2rem 0.5rem;
            border-radius: 6px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }}

        .match-body {{
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
        }}

        .match-info-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.4rem;
        }}

        .info-label {{
            color: var(--text-muted);
        }}

        .info-val {{
            font-weight: 500;
        }}

        .status-winner-a {{ color: var(--accent-a); font-weight: 600; }}
        .status-winner-b {{ color: var(--accent-b); font-weight: 600; }}
        .status-draw {{ color: var(--draw-color); font-weight: 600; }}
        .status-error {{ color: var(--error-color); font-weight: 600; }}

        .error-msg {{
            color: var(--error-color);
            font-size: 0.8rem;
            margin-top: 0.5rem;
            word-break: break-all;
        }}

        .button-group {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.75rem;
        }}

        .vis-btn {{
            background: var(--button-grad);
            color: white;
            border: none;
            padding: 0.6rem 0.5rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.85rem;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.1s;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}

        .vis-btn:hover {{
            background: var(--button-grad-hover);
            transform: scale(1.02);
        }}

        .vis-btn span {{
            font-size: 0.7rem;
            font-weight: normal;
            opacity: 0.8;
            margin-top: 2px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Pokémon TCG AI Battle Dashboard</h1>
        </header>

        <div class="summary-dashboard">
            <div class="summary-agent-a">
                <div class="agent-name">{agent_a} (A)</div>
                <div class="score">{a_wins}</div>
            </div>
            <div class="summary-stats">
                <div class="win-rate">{win_rate_a:.1f}% <span>Win Rate (A)</span></div>
                <div class="details-count">Total: {total} | Draws: {draws} | Errors: {errors}</div>
            </div>
            <div class="summary-agent-b">
                <div class="agent-name">{agent_b} (B)</div>
                <div class="score">{b_wins}</div>
            </div>
        </div>

        <main>
            <div class="match-grid">
"""

    for m in matches_data:
        idx = m["match_idx"]
        turns = m["turns"]
        winner = m["winner"]
        is_player0_a = m["is_player0_a"]
        error = m["error"]

        p0_name = agent_a if is_player0_a else agent_b
        p1_name = agent_b if is_player0_a else agent_a

        if winner == 0:
            result_str = f'<span class="status-winner-a">Winner: {agent_a} (A)</span>'
        elif winner == 1:
            result_str = f'<span class="status-winner-b">Winner: {agent_b} (B)</span>'
        elif winner == -1:
            result_str = '<span class="status-draw">Draw</span>'
        else:
            result_str = '<span class="status-error">Error</span>'

        error_html = f'<div class="error-msg">{error}</div>' if error else ""

        html += f"""
                <div class="match-card">
                    <div>
                        <div class="match-header">
                            <div class="match-title">Match #{idx}</div>
                            <div class="turns-badge">{turns} Turns</div>
                        </div>
                        <div class="match-body">
                            <div class="match-info-row">
                                <span class="info-label">First Player (P0):</span>
                                <span class="info-val">{p0_name}</span>
                            </div>
                            <div class="match-info-row">
                                <span class="info-label">Second Player (P1):</span>
                                <span class="info-val">{p1_name}</span>
                            </div>
                            <div class="match-info-row"
                                 style="margin-top: 0.8rem;
                                        border-top: 1px solid rgba(255,255,255,0.04);
                                        padding-top: 0.5rem;">
                                <span class="info-label">Result:</span>
                                <span class="info-val">{result_str}</span>
                            </div>
                            {error_html}
                        </div>
                    </div>
                    <div class="button-group">
                        <button class="vis-btn" onclick="openHerozVisualizer({idx}, 0)">
                            P0 視点
                            <span>({p0_name[:12]})</span>
                        </button>
                        <button class="vis-btn" onclick="openHerozVisualizer({idx}, 1)">
                            P1 視点
                            <span>({p1_name[:12]})</span>
                        </button>
                    </div>
                </div>
"""

    html += f"""
            </div>
        </main>
    </div>

    <script>
        const matchData = {match_data_json};

        function openHerozVisualizer(matchIdx, playerIndex) {{
            const data = matchData.find(m => m.match_idx === matchIdx);
            if (!data || !data.vis_list) {{
                alert("No visualization data available for this match.");
                return;
            }}

            const visList = data.vis_list;
            const episodeId = data.episode_id;

            const input = document.createElement("input");
            input.type = "hidden";
            input.name = "json";
            input.value = JSON.stringify(visList);

            const form = document.createElement("form");
            form.method = "POST";
            form.action = "https://ptcgvis.heroz.jp/Visualizer/Replay/";
            if (episodeId == null) {{
                form.action += playerIndex;
            }} else {{
                form.action += episodeId + "/" + playerIndex;
            }}
            form.target = "_blank";
            form.appendChild(input);

            document.body.appendChild(form);
            form.submit();
            document.body.removeChild(form);
        }}
    </script>
</body>
</html>
"""
    return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run matches and generate HTML visualizer dashboard."
    )
    parser.add_argument("--agent-a", required=True, help="Path to agent A python file")
    parser.add_argument("--agent-b", required=True, help="Path to agent B python file")
    parser.add_argument(
        "--output", default="scratch/visualizer.html", help="Path to output HTML file"
    )
    parser.add_argument(
        "--matches",
        type=int,
        default=10,
        help="Number of consecutive matches to play (default: 10)",
    )
    args = parser.parse_args()

    # Automatically patch kaggle-environments with the local simulation engine
    patch_kaggle_environments()

    # Set PTCG_PROJECT_ROOT to the repository root
    os.environ["PTCG_PROJECT_ROOT"] = project_root

    matches_count = args.matches
    output_path = os.path.abspath(args.output)
    base_dir = os.path.dirname(output_path)

    # フォルダのクリーンチェック
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)

    agent_a_name = os.path.basename(os.path.dirname(args.agent_a))
    agent_b_name = os.path.basename(os.path.dirname(args.agent_b))

    print(f"Starting {matches_count} matches simulation...")
    print(f"Agent A: {args.agent_a}")
    print(f"Agent B: {args.agent_b}")

    # multiprocessing のコンテキストとして 'spawn' を使用（C++ライブラリの状態競合を回避するため）
    ctx = multiprocessing.get_context("spawn")

    for i in range(matches_count):
        match_idx = i + 1
        is_player0_a = i % 2 == 0

        # 一時JSONファイルのパス
        temp_json_path = os.path.join(base_dir, f"_temp_match_{match_idx}.json")

        print(f"Running match {match_idx}/{matches_count}...")

        p = ctx.Process(
            target=run_and_save_match,
            args=(
                args.agent_a,
                args.agent_b,
                temp_json_path,
                is_player0_a,
                match_idx,
            ),
        )
        p.start()
        p.join()

        if p.exitcode != 0:
            print(f"Error executing match {match_idx}. Exit code: {p.exitcode}")
            sys.exit(1)

    # 全対戦データの回収と集約
    matches_data = []
    for i in range(matches_count):
        match_idx = i + 1
        temp_json_path = os.path.join(base_dir, f"_temp_match_{match_idx}.json")
        if os.path.exists(temp_json_path):
            with open(temp_json_path, "r", encoding="utf-8") as f:
                matches_data.append(json.load(f))
            try:
                os.remove(temp_json_path)
            except Exception:
                pass

    # 集計
    a_wins = sum(1 for m in matches_data if m["winner"] == 0)
    b_wins = sum(1 for m in matches_data if m["winner"] == 1)
    draws = sum(1 for m in matches_data if m["winner"] == -1)
    errors = sum(1 for m in matches_data if m["winner"] == -2)

    # HTMLダッシュボードの生成
    html_content = generate_dashboard_html(
        agent_a_name,
        agent_b_name,
        matches_data,
        a_wins,
        b_wins,
        draws,
        errors,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nDone. Saved visualization dashboard to {output_path}")
    print("Please open the file in a web browser to view match list and replays.")


if __name__ == "__main__":
    main()
