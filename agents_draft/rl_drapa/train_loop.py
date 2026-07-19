"""本番トレーニングスクリプト。

ローカル GPU (RTX 5060 Ti) / GCP (L4 GPU + c2-standard-32) の
両環境で実行可能な自己対戦 + PPO 学習ループ。

仕様書に基づき、以下の機能を実装：
1. バグ修正：ゲーム内の先攻・後攻をランダムに決定し、自分側のターンのみ学習バッファにデータを蓄積。
2. カリキュラム学習：エピソード進行状況や勝率に応じて対戦相手（StarEx, DragonBomb, sample_iono, Random）を切り替え。
3. 破滅的忘却対策 (計画B-2)：弱いルールベース（DragonBomb）から簡易ILデータを自己生成して Behavioral Cloning 事前学習を実行。
   さらに、強化学習中に事前学習した IL モデルとの逆KLダイバージェンス正則化を適用し、フェーズ2の進行に伴いアニーリング線形減衰させる。
"""

import argparse
import csv
import os
import random
import signal
import sys
import time
from collections import deque
from typing import Any, Callable

# パス設定
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.environ.setdefault("PTCG_PROJECT_ROOT", SCRIPT_DIR)

# プロジェクトルートを sys.path に追加して tests.utils をロードできるようにする
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import torch
from torch import Tensor

from cg.api import all_attack, all_card_data, to_observation_class
from cg.game import battle_finish, battle_select, battle_start
from tests.utils import load_agent, load_deck

from action_encoder import encode_actions
from config import PPO, REWARD
from network import ActorCritic
from reward import RewardCalculator
from state_encoder import encode_state
from training import PPOTrainer, RolloutBuffer

# ---------------------------------------------------------------------------
# グレースフルシャットダウン
# ---------------------------------------------------------------------------
_shutdown_requested = False


def _signal_handler(signum: int, frame: Any) -> None:
    """シグナル受信時にシャットダウンフラグを立てる。"""
    global _shutdown_requested
    print(
        f"\n[SIGNAL] {signum} を受信しました。"
        "現在のゲーム終了後にチェックポイントを保存して終了します..."
    )
    _shutdown_requested = True


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _find_latest_checkpoint(checkpoint_dir: str) -> str | None:
    """チェックポイントディレクトリから最新のチェックポイントを探す。"""
    latest = os.path.join(checkpoint_dir, "latest.pt")
    if os.path.exists(latest):
        return latest
    if not os.path.isdir(checkpoint_dir):
        return None
    pts = [
        f
        for f in os.listdir(checkpoint_dir)
        if f.startswith("checkpoint_") and f.endswith(".pt")
    ]
    if not pts:
        return None
    pts.sort(key=lambda x: int(x.replace("checkpoint_", "").replace(".pt", "")))
    return os.path.join(checkpoint_dir, pts[-1])


def _print_memory() -> None:
    """GPU / CPU メモリ使用量を表示する。"""
    if torch.cuda.is_available():
        alloc = torch.cuda.memory_allocated() / 1024**2
        reserved = torch.cuda.memory_reserved() / 1024**2
        print(f"  [Memory] GPU: {alloc:.0f} MB allocated, {reserved:.0f} MB reserved")
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    print(f"  [Memory] CPU RSS: {rss_kb / 1024:.0f} MB")
                    break
    except (FileNotFoundError, ValueError):
        pass


# ---------------------------------------------------------------------------
# パラメータのアニーリング計算
# ---------------------------------------------------------------------------


def get_annealed_params(
    episode: int,
    current_phase: int,
    base_beta: float = REWARD.beta_potential,
    base_lambda_kl: float = 0.01,  # 計画B-2: 通常の1/10
    phase2_start: int = 100000,
    phase3_start: int = 300000,
) -> tuple[float, float]:
    """エピソード数とフェーズに応じたポテンシャル係数βと逆KL正則化係数のアニーリング線形減衰を計算。"""
    if current_phase == 1:
        return base_beta, base_lambda_kl
    elif current_phase == 2:
        progress = (episode - phase2_start) / max(phase3_start - phase2_start, 1)
        progress = min(max(progress, 0.0), 1.0)
        # 線形減衰
        beta = base_beta * (1.0 - progress)
        lambda_kl = base_lambda_kl * (1.0 - progress)
        return beta, lambda_kl
    else:
        # フェーズ3では完全にゼロ
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# 簡易模倣学習（IL）データ収集 & 事前学習 (計画B-2)
# ---------------------------------------------------------------------------


def collect_il_data(
    rule_based_agent_path: str,
    deck: list[int],
    card_data_map: dict[int, Any],
    attack_map: dict[int, Any],
    num_games: int = 200,
) -> list[dict[str, Any]]:
    """ルールベースエージェントの対局から状態と行動のペアを自己生成して収集する。"""
    print(f"🎮 簡易ILデータを収集しています... (ルールベース対戦: {num_games} 試合)")
    agent_func = load_agent(rule_based_agent_path)
    collected_data = []

    for _game_i in range(num_games):
        obs_dict, _ = battle_start(deck, deck)
        game_ended = False
        steps = 0
        try:
            while steps < 500 and not game_ended:
                obs = to_observation_class(obs_dict)
                if obs.select is None:
                    obs_dict = battle_select(deck)
                    steps += 1
                    continue

                # 現在の状態特徴量をエンコード
                sd = encode_state(obs, card_data_map)
                ad = encode_actions(obs.select.option, obs, attack_map)

                # ルールベースエージェントの選択
                choices = agent_func(obs_dict)
                act_idx = choices[0] if choices else 0

                collected_data.append({
                    "state_dict": sd,
                    "action_type_ids": ad["action_type_ids"],
                    "target_card_ids": ad["target_card_ids"],
                    "target_position": ad["target_position"],
                    "meta_features": ad["meta_features"],
                    "action_mask": ad["action_mask"],
                    "action": torch.tensor(act_idx, dtype=torch.long),
                })

                obs_dict = battle_select(choices)
                steps += 1

                obs_check = to_observation_class(obs_dict)
                for log in obs_check.logs:
                    lt = log.type
                    if hasattr(lt, "value"):
                        lt = lt.value
                    if lt == 23:
                        game_ended = True
                        break
        finally:
            battle_finish()

    print(f"✅ 簡易ILデータ収集完了: {len(collected_data)} ステップ")
    return collected_data


def pretrain_model(
    model: ActorCritic,
    trainer: PPOTrainer,
    il_data: list[dict[str, Any]],
    epochs: int = 5,
    batch_size: int = 64,
) -> None:
    """収集した簡易ILデータを用いてモデルを事前学習 (Behavioral Cloning) する。"""
    print(f"🔥 事前学習 (Behavioral Cloning) を開始します... ({epochs} エポック)")
    t = len(il_data)

    for epoch in range(epochs):
        perm = torch.randperm(t).tolist()
        epoch_loss = 0.0
        steps = 0

        for start in range(0, t, batch_size):
            end = min(start + batch_size, t)
            batch_indices = perm[start:end]
            if not batch_indices:
                continue

            batch_state = trainer._batch_state_dicts(
                [il_data[i]["state_dict"] for i in batch_indices]
            )
            batch_action_type = torch.stack(
                [il_data[i]["action_type_ids"] for i in batch_indices]
            ).to(trainer.device)
            batch_card_ids = torch.stack(
                [il_data[i]["target_card_ids"] for i in batch_indices]
            ).to(trainer.device)
            batch_positions = torch.stack(
                [il_data[i]["target_position"] for i in batch_indices]
            ).to(trainer.device)
            batch_meta = torch.stack(
                [il_data[i]["meta_features"] for i in batch_indices]
            ).to(trainer.device)
            batch_masks = torch.stack(
                [il_data[i]["action_mask"] for i in batch_indices]
            ).to(trainer.device)
            batch_actions = torch.stack(
                [il_data[i]["action"] for i in batch_indices]
            ).to(trainer.device)

            loss = trainer.pretrain_step(
                batch_state,
                batch_action_type,
                batch_card_ids,
                batch_positions,
                batch_meta,
                batch_masks,
                batch_actions,
            )
            epoch_loss += loss
            steps += 1

        avg_loss = epoch_loss / max(steps, 1)
        print(f"  [Epoch {epoch+1}/{epochs}] BC Loss: {avg_loss:.4f}")


# ---------------------------------------------------------------------------
# 対局の実行 (自己対戦 / 他エージェント対戦対応)
# ---------------------------------------------------------------------------


def play_one_game(
    model: ActorCritic,
    your_deck: list[int],
    opponent_agent: Callable[[dict], list[int]] | None,  # None の場合は自己対戦 (学習中モデル)
    opponent_deck: list[int],
    card_data_map: dict[int, Any],
    attack_map: dict[int, Any],
    buffer: RolloutBuffer,
    device: str = "cpu",
    your_player_index: int = 0,
    beta_potential: float = REWARD.beta_potential,
) -> dict[str, Any]:
    """1対戦を実行し、自分の意思決定の経験データのみをバッファに蓄積。"""
    if your_player_index == 0:
        obs_dict, _ = battle_start(your_deck, opponent_deck)
    else:
        obs_dict, _ = battle_start(opponent_deck, your_deck)

    # 報酬計算器の初期化
    reward_calc = RewardCalculator(your_index=your_player_index, beta=beta_potential)
    total_reward = 0.0
    steps = 0
    game_result = -1
    game_ended = False

    try:
        while steps < 500 and not game_ended:
            obs = to_observation_class(obs_dict)
            if obs.select is None:
                # 初期セットアップ等の自動選択
                current_player = obs.current.yourIndex if obs.current else 0
                if current_player == your_player_index:
                    obs_dict = battle_select(your_deck)
                else:
                    obs_dict = battle_select(opponent_deck)
                steps += 1
                continue

            current_player = obs.current.yourIndex if obs.current else your_player_index

            if current_player == your_player_index:
                # 自分のターン -> モデル推論を実行し、バッファに追加
                sd = encode_state(obs, card_data_map)
                ad = encode_actions(obs.select.option, obs, attack_map)
                batched = {k: v.unsqueeze(0).to(device) for k, v in sd.items()}

                with torch.no_grad():
                    action, log_prob, entropy, value = model.get_action_and_value(
                        batched,
                        ad["action_type_ids"].unsqueeze(0).to(device),
                        ad["target_card_ids"].unsqueeze(0).to(device),
                        ad["target_position"].unsqueeze(0).to(device),
                        ad["meta_features"].unsqueeze(0).to(device),
                        ad["action_mask"].unsqueeze(0).to(device),
                    )

                reward, done = reward_calc.calculate(obs)
                total_reward += reward

                buffer.add(
                    state_dict=sd,
                    action_type_ids=ad["action_type_ids"],
                    target_card_ids=ad["target_card_ids"],
                    target_position=ad["target_position"],
                    meta_features=ad["meta_features"],
                    action_mask=ad["action_mask"],
                    action=action.squeeze(0).cpu(),
                    log_prob=log_prob.squeeze(0).cpu(),
                    reward=reward,
                    value=value.squeeze(0).cpu(),
                    done=done,
                )

                act_idx = action.item()
                n = len(obs.select.option)
                act_idx = min(act_idx, n - 1)
                k = min(obs.select.maxCount, n)
                if k == 1:
                    choices = [act_idx]
                else:
                    choices = random.sample(range(n), k)
                obs_dict = battle_select(choices)

            else:
                # 相手のターン
                if opponent_agent is None:
                    # 自己対戦 (学習モデルを適用するが、バッファには追加しない)
                    sd = encode_state(obs, card_data_map)
                    ad = encode_actions(obs.select.option, obs, attack_map)
                    batched = {k: v.unsqueeze(0).to(device) for k, v in sd.items()}

                    with torch.no_grad():
                        action, _, _, _ = model.get_action_and_value(
                            batched,
                            ad["action_type_ids"].unsqueeze(0).to(device),
                            ad["target_card_ids"].unsqueeze(0).to(device),
                            ad["target_position"].unsqueeze(0).to(device),
                            ad["meta_features"].unsqueeze(0).to(device),
                            ad["action_mask"].unsqueeze(0).to(device),
                        )
                    act_idx = action.item()
                    n = len(obs.select.option)
                    act_idx = min(act_idx, n - 1)
                    k = min(obs.select.maxCount, n)
                    if k == 1:
                        choices = [act_idx]
                    else:
                        choices = random.sample(range(n), k)
                    obs_dict = battle_select(choices)
                else:
                    # 他エージェント (外部モジュール) を呼び出す
                    choices = opponent_agent(obs_dict)
                    obs_dict = battle_select(choices)

            steps += 1

            # ゲーム終了判定
            obs_check = to_observation_class(obs_dict)
            for log in obs_check.logs:
                lt = log.type
                if hasattr(lt, "value"):
                    lt = lt.value
                if lt == 23:  # RESULT
                    game_result = log.result
                    game_ended = True
                    # 最終ステップ報酬
                    final_r, _ = reward_calc.calculate(obs_check)
                    total_reward += final_r
                    break

    finally:
        battle_finish()

    won = game_result == your_player_index

    return {
        "steps": steps,
        "result": game_result,
        "won": won,
        "total_reward": total_reward,
    }


# ---------------------------------------------------------------------------
# メイン学習ループ
# ---------------------------------------------------------------------------


def main() -> None:
    """メイン学習ループ。"""
    parser = argparse.ArgumentParser(description="RL Agent Training with Curriculum")
    parser.add_argument("--num-games", type=int, default=10000, help="学習対戦数")
    parser.add_argument(
        "--update-every", type=int, default=5, help="PPO更新間隔 (ゲーム数)"
    )
    parser.add_argument("--device", type=str, default="cuda", help="デバイス (cpu/cuda)")
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="checkpoints",
        help="チェックポイント保存先",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=200,
        help="チェックポイント保存間隔 (ゲーム数)",
    )
    parser.add_argument(
        "--resume", type=str, default=None, help="再開用チェックポイントパス"
    )
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        help="最新のチェックポイントから自動的に再開",
    )
    parser.add_argument("--lr", type=float, default=PPO.learning_rate, help="学習率")
    parser.add_argument(
        "--window", type=int, default=50, help="勝率評価用の移動平均窓"
    )
    parser.add_argument(
        "--pretrain-games", type=int, default=200, help="事前学習データ収集用の自己対戦ゲーム数"
    )
    parser.add_argument(
        "--pretrain-epochs", type=int, default=5, help="事前学習 (BC) のエポック数"
    )
    parser.add_argument(
        "--skip-pretrain",
        action="store_true",
        help="簡易IL事前学習をスキップして直接強化学習を開始する",
    )
    args = parser.parse_args()

    # シグナルハンドラ登録
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("[WARN] CUDA is not available, falling back to CPU")
        device = "cpu"

    checkpoint_dir = args.checkpoint_dir
    log_dir = os.path.join(checkpoint_dir, "logs")
    os.makedirs(checkpoint_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    print("=" * 60)
    print("🐉 ドラパルトex + カースドボム RL カリキュラム学習")
    print("=" * 60)
    print(f"  Device           : {device}")
    print(f"  Num games        : {args.num_games}")
    print(f"  Update every     : {args.update_every} games")
    print(f"  Checkpoint every : {args.checkpoint_interval} games")
    print(f"  Learning rate    : {args.lr}")
    print(f"  Checkpoint dir   : {checkpoint_dir}")
    print("=" * 60)

    # 1. 共通マッピングの読み込み
    card_data_map = {cd.cardId: cd for cd in all_card_data()}
    attack_map = {atk.attackId: atk for atk in all_attack()}
    deck = load_deck(SCRIPT_DIR)

    # 2. モデル初期化
    model = ActorCritic()
    il_model = None

    # 事前学習 (Behavioral Cloning) のトリガー (チェックポイント再開でない場合)
    resume_path = args.resume
    if resume_path is None and args.auto_resume:
        resume_path = _find_latest_checkpoint(checkpoint_dir)

    is_resumed = resume_path and os.path.exists(resume_path)

    # 他の対戦相手パス設定
    opponent_paths = {
        "StarEx": os.path.join(PROJECT_ROOT, "agents", "StarEx", "main.py"),
        "DragonBomb": os.path.join(PROJECT_ROOT, "agents", "DragonBomb", "main.py"),
        "IonoBellibolt": os.path.join(
            PROJECT_ROOT, "sample_deck", "sample_iono", "main.py"
        ),
        "Random": os.path.join(PROJECT_ROOT, "sample_submission", "main.py"),
    }

    # 事前学習フェーズ
    if not is_resumed and not args.skip_pretrain:
        # ルールベース (DragonBomb) からデータを収集
        il_data = collect_il_data(
            opponent_paths["DragonBomb"],
            deck,
            card_data_map,
            attack_map,
            num_games=args.pretrain_games,
        )
        pretrain_trainer = PPOTrainer(model, lr=args.lr, device=device)
        pretrain_model(model, pretrain_trainer, il_data, epochs=args.pretrain_epochs, batch_size=64)

        # 事前学習済みの重みを IL ターゲットモデルとして保存
        il_model_path = os.path.join(checkpoint_dir, "il_model.pt")
        torch.save(model.state_dict(), il_model_path)
        print(f"💾 模倣学習初期モデル保存: {il_model_path}")

    # IL モデルのロード (逆KL計算用)
    il_model_path = os.path.join(checkpoint_dir, "il_model.pt")
    if os.path.exists(il_model_path):
        il_model = ActorCritic()
        il_model.load_state_dict(torch.load(il_model_path, map_location=device))
        il_model = il_model.to(device)
        print("✅ 逆KL正則化ターゲット (IL_Model) ロード完了")

    start_game = 0
    best_win_rate = 0.0

    if is_resumed:
        print(f"\n📂 チェックポイントから再開: {resume_path}")
        cp = torch.load(resume_path, map_location=device, weights_only=False)
        model.load_state_dict(cp["model_state_dict"])
        start_game = cp.get("episode", 0)
        best_win_rate = cp.get("best_win_rate", 0.0)

    model = model.to(device)
    trainer = PPOTrainer(model, lr=args.lr, device=device, il_model=il_model)

    if is_resumed:
        trainer.optimizer.load_state_dict(cp["optimizer_state_dict"])  # type: ignore[possibly-undefined]

    buffer = RolloutBuffer()

    # 対戦相手エージェントとデッキのロード (オンメモリキャッシュ)
    print("\n👾 対戦相手エージェントをロードしています...")
    opponents = {}
    opponent_decks = {}
    for name, path in opponent_paths.items():
        if os.path.exists(path):
            opponents[name] = load_agent(path)
            opponent_decks[name] = load_deck(os.path.dirname(path))
            print(f"  ✅ {name} ロード完了 (デッキ: {len(opponent_decks[name])}枚)")
        else:
            print(f"  ❌ {name} が見つかりません: {path}")

    # CSV ログ初期化
    episode_csv_path = os.path.join(log_dir, "episodes.csv")
    update_csv_path = os.path.join(log_dir, "updates.csv")
    ep_exists = os.path.exists(episode_csv_path)
    up_exists = os.path.exists(update_csv_path)

    ep_file = open(episode_csv_path, "a", newline="")
    up_file = open(update_csv_path, "a", newline="")
    ep_writer = csv.writer(ep_file)
    up_writer = csv.writer(up_file)

    if not ep_exists:
        ep_writer.writerow(
            ["episode", "won", "total_reward", "steps", "opponent", "phase"]
        )
    if not up_exists:
        up_writer.writerow([
            "episode",
            "policy_loss",
            "value_loss",
            "entropy",
            "kl_div",
            "win_rate_ma",
            "beta",
            "lambda_kl",
        ])

    try:
        from tqdm import tqdm

        use_tqdm = True
    except ImportError:
        use_tqdm = False

    # カリキュラム学習用の統計
    wins = 0
    total_reward_sum = 0.0
    wins_window: deque[int] = deque(maxlen=args.window)
    recent_records: dict[str, list[int]] = {
        name: [] for name in opponent_paths.keys()
    }
    recent_records["SelfPlay"] = []

    t_start = time.time()
    end_game = start_game + args.num_games

    if use_tqdm:
        pbar = tqdm(
            total=args.num_games,
            desc="Training",
            unit="game",
        )

    # 学習ループ
    for game_i in range(start_game, end_game):
        if _shutdown_requested:
            print("\n[SHUTDOWN] Graceful shutdown requested.")
            break

        # --- カリキュラムフェーズの決定 ---
        # weighted_winrate (ミラー除く)
        starex_wr = (
            sum(recent_records["StarEx"][-50:])
            / max(len(recent_records["StarEx"][-50:]), 1)
            if recent_records["StarEx"]
            else 0.0
        )
        iono_wr = (
            sum(recent_records["IonoBellibolt"][-50:])
            / max(len(recent_records["IonoBellibolt"][-50:]), 1)
            if recent_records["IonoBellibolt"]
            else 0.0
        )
        random_wr = (
            sum(recent_records["Random"][-50:])
            / max(len(recent_records["Random"][-50:]), 1)
            if recent_records["Random"]
            else 0.0
        )

        weighted_wr_ex_mirror = starex_wr * 0.7 + iono_wr * 0.2 + random_wr * 0.1

        # ミラー含む全体の勝率
        mirror_wr = (
            sum(recent_records["DragonBomb"][-50:])
            / max(len(recent_records["DragonBomb"][-50:]), 1)
            if recent_records["DragonBomb"]
            else 0.0
        )
        weighted_wr_inc_mirror = (
            starex_wr * 0.4 + mirror_wr * 0.3 + iono_wr * 0.2 + random_wr * 0.1
        )

        # フェーズ判定 (仕様書5.3節)
        current_phase = 1
        if game_i >= 300000 or (game_i >= 100000 and weighted_wr_inc_mirror > 0.55):
            current_phase = 3
        elif game_i >= 100000 or (
            game_i >= 20000 and weighted_wr_ex_mirror > 0.35
        ):
            current_phase = 2

        # 対戦相手の選択 (Curriculum weights)
        opponent_name = "SelfPlay"
        if current_phase == 1:
            # StarEx 70%, Iono 20%, Random 10%
            r = random.random()
            if r < 0.70:
                opponent_name = "StarEx"
            elif r < 0.90:
                opponent_name = "IonoBellibolt"
            else:
                opponent_name = "Random"
        elif current_phase == 2:
            # StarEx 40%, DragonBomb (Mirror) 30%, Iono 20%, Random 10%
            r = random.random()
            if r < 0.40:
                opponent_name = "StarEx"
            elif r < 0.70:
                opponent_name = "DragonBomb"
            elif r < 0.90:
                opponent_name = "IonoBellibolt"
            else:
                opponent_name = "Random"
        else:
            # フェーズ3: 自己対戦 90%, StarEx 5%, DragonBomb 5%
            r = random.random()
            if r < 0.90:
                opponent_name = "SelfPlay"
            elif r < 0.95:
                opponent_name = "StarEx"
            else:
                opponent_name = "DragonBomb"

        # アニーリングパラメータ計算
        beta, lambda_kl = get_annealed_params(game_i, current_phase)

        # 対戦相手の関数とデッキの決定
        opp_agent = (
            opponents.get(opponent_name) if opponent_name != "SelfPlay" else None
        )
        opp_deck = opponent_decks.get(opponent_name, deck)

        # 先攻後攻のランダム決定 (0 = 自分先攻, 1 = 自分後攻)
        your_index = random.randint(0, 1)

        # 1ゲーム対戦を実行
        model.eval()
        result = play_one_game(
            model=model,
            your_deck=deck,
            opponent_agent=opp_agent,
            opponent_deck=opp_deck,
            card_data_map=card_data_map,
            attack_map=attack_map,
            buffer=buffer,
            device=device,
            your_player_index=your_index,
            beta_potential=beta,
        )

        won = result["won"]
        wins_window.append(1 if won else 0)
        recent_records[opponent_name].append(1 if won else 0)
        if won:
            wins += 1
        total_reward_sum += result["total_reward"]

        ma_win_rate = sum(wins_window) / len(wins_window)

        # CSV エピソードログ書き出し
        ep_writer.writerow([
            game_i + 1,
            int(won),
            f"{result['total_reward']:.4f}",
            result["steps"],
            opponent_name,
            current_phase,
        ])
        ep_file.flush()

        if use_tqdm:
            pbar.update(1)
            pbar.set_postfix(
                PH=current_phase,
                opp=opponent_name,
                WR=f"{ma_win_rate:.1%}",
                R=f"{result['total_reward']:.2f}",
            )

        # --- PPO アップデート ---
        if (game_i + 1) % args.update_every == 0 and len(buffer) > 0:
            model.train()
            metrics = trainer.update(buffer, last_value=0.0, lambda_kl=lambda_kl)
            buffer.clear()

            # CSV アップデートログ書き出し
            up_writer.writerow([
                game_i + 1,
                f"{metrics['policy_loss']:.6f}",
                f"{metrics['value_loss']:.6f}",
                f"{metrics['entropy']:.6f}",
                f"{metrics['kl_div']:.6f}",
                f"{ma_win_rate:.4f}",
                f"{beta:.4f}",
                f"{lambda_kl:.4f}",
            ])
            up_file.flush()

            if not use_tqdm:
                elapsed = time.time() - t_start
                games_done = game_i + 1 - start_game
                print(
                    f"[Game {game_i + 1}] Phase={current_phase} Opp={opponent_name} "
                    f"WR(MA)={ma_win_rate:.3f} AvgR={total_reward_sum/games_done:.3f} "
                    f"PL={metrics['policy_loss']:.4f} VL={metrics['value_loss']:.4f} "
                    f"KL={metrics['kl_div']:.4f} beta={beta:.3f} lam={lambda_kl:.4f} ({elapsed:.1f}s)"
                )

        # --- 最良モデルの保存 ---
        if len(wins_window) >= args.window and ma_win_rate > best_win_rate:
            best_win_rate = ma_win_rate
            best_path = os.path.join(checkpoint_dir, "best_model.pt")
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": trainer.optimizer.state_dict(),
                    "episode": game_i + 1,
                    "best_win_rate": best_win_rate,
                    "metrics": {"win_rate": best_win_rate},
                },
                best_path,
            )
            msg = f"  [BEST] New best win rate: {best_win_rate:.1%} (ep={game_i + 1})"
            if use_tqdm:
                tqdm.write(msg)
            else:
                print(msg)

        # --- 定期チェックポイント ---
        if (game_i + 1) % args.checkpoint_interval == 0:
            elapsed = time.time() - t_start
            games_done = game_i + 1 - start_game
            avg_r = total_reward_sum / games_done

            save_dict = {
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": trainer.optimizer.state_dict(),
                "episode": game_i + 1,
                "best_win_rate": best_win_rate,
                "metrics": {
                    "win_rate_ma": ma_win_rate,
                    "avg_reward": avg_r,
                    "phase": current_phase,
                },
            }

            cp_path = os.path.join(checkpoint_dir, f"checkpoint_{game_i + 1}.pt")
            torch.save(save_dict, cp_path)

            latest_path = os.path.join(checkpoint_dir, "latest.pt")
            torch.save(save_dict, latest_path)

            msg = (
                f"  [SAVE] ep={game_i + 1}, Phase={current_phase}, "
                f"WR(MA)={ma_win_rate:.1%}, AvgR={avg_r:.3f}, {elapsed:.0f}s"
            )
            if use_tqdm:
                tqdm.write(msg)
            else:
                print(msg)
            _print_memory()

    if use_tqdm:
        pbar.close()
    ep_file.close()
    up_file.close()

    # 最終モデルの保存
    final_ep = game_i + 1 if "game_i" in dir() else start_game  # type: ignore[possibly-undefined]
    latest_path = os.path.join(checkpoint_dir, "latest.pt")
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": trainer.optimizer.state_dict(),
            "episode": final_ep,
            "best_win_rate": best_win_rate,
        },
        latest_path,
    )

    inference_path = os.path.join(SCRIPT_DIR, "model.pt")
    torch.save(model.state_dict(), inference_path)

    elapsed = time.time() - t_start
    total_games = final_ep - start_game
    winrate = wins / max(total_games, 1)
    avg_reward = total_reward_sum / max(total_games, 1)

    print("\n" + "=" * 60)
    print("Curriculum Training Complete")
    print("=" * 60)
    print(f"  Total games    : {total_games}")
    print(f"  Overall WR     : {winrate:.1%}")
    print(f"  Best WR (MA)   : {best_win_rate:.1%}")
    print(f"  Avg reward     : {avg_reward:.3f}")
    print(f"  Elapsed        : {elapsed:.0f}s ({elapsed / 60:.1f} min)")
    if total_games > 0:
        print(f"  Throughput     : {total_games / max(elapsed, 0.1):.1f} games/s")
    print(f"  Latest Ckpt    : {latest_path}")
    print(f"  Inference Model: {inference_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
