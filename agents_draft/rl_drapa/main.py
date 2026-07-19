"""RL エージェント推論エントリーポイント。

Kaggle 提出環境および ローカル検証環境の両方で動作する。
学習済みモデル (model.pt) が存在する場合はそれを使用し、
存在しない場合はランダムエージェントとして動作する。
"""

import os
import random
from typing import Any


# --- デッキ読み込み ---
def read_deck_csv() -> list[int]:
    """deck.csv からデッキのカードIDリストを読み込む。

    Returns:
        60枚のカードIDリスト。
    """
    file_path = "deck.csv"
    if not os.path.exists(file_path):
        file_path = "/kaggle_simulations/agent/" + file_path
    with open(file_path, "r") as file:
        csv = file.read().split("\n")
    deck: list[int] = []
    for i in range(60):
        deck.append(int(csv[i]))
    return deck


# --- グローバル初期化 (モデル・カードデータの遅延ロード) ---
_model: Any = None
_card_data_map: dict[int, Any] = {}
_attack_map: dict[int, Any] = {}
_initialized = False


def _initialize() -> None:
    """モデルとカードデータを遅延ロードする。"""
    global _model, _initialized

    if _initialized:
        return
    _initialized = True

    try:
        import torch
        from cg.api import all_card_data, all_attack

        # カードデータマップの構築
        try:
            card_data_list = all_card_data()
            _card_data_map.update({cd.cardId: cd for cd in card_data_list})
        except Exception:
            pass  # カードデータが取得できない場合は空辞書で続行

        # 攻撃データマップの構築
        try:
            attack_list = all_attack()
            _attack_map.update({atk.attackId: atk for atk in attack_list})
        except Exception:
            pass

        # 学習済みモデルの読み込み
        model_path = "model.pt"
        if not os.path.exists(model_path):
            model_path = "/kaggle_simulations/agent/" + model_path

        if os.path.exists(model_path):
            try:
                from .network import ActorCritic
            except ImportError:
                from network import ActorCritic  # type: ignore[no-redef]

            model = ActorCritic()
            checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
            if "model_state_dict" in checkpoint:
                model.load_state_dict(checkpoint["model_state_dict"])
            else:
                model.load_state_dict(checkpoint)
            model.eval()
            _model = model

    except ImportError:
        # torch が利用できない場合はランダムエージェント
        pass
    except Exception:
        pass


def agent(obs_dict: dict) -> list[int]:
    """RL エージェントのメイン関数。

    Args:
        obs_dict: 生の観測辞書。

    Returns:
        選択肢インデックスのリスト。
    """
    from cg.api import to_observation_class, Observation

    obs: Observation = to_observation_class(obs_dict)

    if obs.select is None:
        # 初期デッキ選択
        return read_deck_csv()

    # 遅延初期化
    _initialize()

    # モデルが利用可能な場合は推論
    if _model is not None:
        try:
            return _inference(obs)
        except Exception:
            pass

    # フォールバック: ランダム選択
    return random.sample(list(range(len(obs.select.option))), obs.select.maxCount)


def _inference(obs: Any) -> list[int]:
    """学習済みモデルによる推論。

    Args:
        obs: Observation オブジェクト。

    Returns:
        選択肢インデックスのリスト。
    """
    import torch

    try:
        from .state_encoder import encode_state
        from .action_encoder import encode_actions
    except ImportError:
        from state_encoder import encode_state  # type: ignore[no-redef]
        from action_encoder import encode_actions  # type: ignore[no-redef]

    # 状態エンコード
    state_dict = encode_state(obs, _card_data_map)

    # バッチ次元の追加
    batched_state: dict[str, torch.Tensor] = {}
    for key, val in state_dict.items():
        batched_state[key] = val.unsqueeze(0)

    # アクションエンコード
    options = obs.select.option
    action_data = encode_actions(options, obs, _attack_map)

    # バッチ次元の追加 (encode_actions の戻り値は Tensor)
    action_type_ids = action_data["action_type_ids"].unsqueeze(0)  # type: ignore[union-attr]
    target_card_ids = action_data["target_card_ids"].unsqueeze(0)  # type: ignore[union-attr]
    target_position = action_data["target_position"].unsqueeze(0)  # type: ignore[union-attr]
    meta_features = action_data["meta_features"].unsqueeze(0)  # type: ignore[union-attr]
    action_mask = action_data["action_mask"].unsqueeze(0)  # type: ignore[union-attr]

    # 推論 (勾配計算不要)
    with torch.no_grad():
        action, _log_prob, _entropy, _value = _model.get_action_and_value(
            batched_state,
            action_type_ids,
            target_card_ids,
            target_position,
            meta_features,
            action_mask,
            deterministic=True,
        )

    action_idx = action.item()

    # 有効範囲チェック
    if action_idx >= len(options):
        action_idx = 0

    # minCount/maxCount に準拠したリストを返す
    min_count = obs.select.minCount
    max_count = obs.select.maxCount

    if min_count == max_count == 1:
        return [action_idx]

    # 複数選択が必要な場合の処理
    # ポインターネットワークは単一選択を返すため、
    # 複数選択が必要な場合は上位 N 件を返す
    with torch.no_grad():
        logits, _ = _model.forward(
            batched_state,
            action_type_ids,
            target_card_ids,
            target_position,
            meta_features,
            action_mask,
        )

    logits = logits.squeeze(0)  # [N]
    num_valid = action_data["num_valid"]
    valid_logits = logits[:num_valid]

    # 上位 max_count 件のインデックスを取得
    k = min(max_count, num_valid)
    _, top_indices = valid_logits.topk(k)
    result = top_indices.tolist()

    # min_count を満たすか確認
    while len(result) < min_count:
        for i in range(num_valid):
            if i not in result:
                result.append(i)
                break
            if len(result) >= min_count:
                break

    return result[:max_count]
