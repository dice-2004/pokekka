"""アクションエンコーダー: 選択肢リスト → アクション特徴量テンソル。

仕様書4.1節に基づき、各選択肢 (Option) を 72次元の固定長ベクトルに
エンコードする。内訳:
  - アクションタイプ ID (Embedding用、整数) → 16次元
  - 対象カード ID (共有 Embedding 用、整数) → 32次元
  - 対象位置 1-hot → 16次元
  - 追加メタデータ → 8次元
"""

from typing import Any

import torch

try:
    from .config import DIMS, NORM
except ImportError:
    from config import DIMS, NORM  # type: ignore[no-redef]


# --- アクションタイプマッピング (OptionType値 → 12分類) ---
# PLAY=0, ATTACH=1, EVOLVE=2, ABILITY=3, DISCARD=4, RETREAT=5,
# ATTACK=6, END=7, CARD=8, YES_NO=9, NUMBER=10, SPECIAL_CONDITION=11
_OPTION_TO_ACTION_TYPE: dict[int, int] = {
    7: 0,  # PLAY → 0
    8: 1,  # ATTACH → 1
    9: 2,  # EVOLVE → 2
    10: 3,  # ABILITY → 3
    11: 4,  # DISCARD → 4
    12: 5,  # RETREAT → 5
    13: 6,  # ATTACK → 6
    14: 7,  # END → 7
    3: 8,  # CARD → 8
    4: 8,  # TOOL_CARD → 8
    5: 8,  # ENERGY_CARD → 8
    6: 8,  # ENERGY → 8
    15: 8,  # SKILL → 8
    1: 9,  # YES → 9
    2: 9,  # NO → 9
    0: 10,  # NUMBER → 10
    16: 11,  # SPECIAL_CONDITION → 11
}

# --- AreaType 定数 ---
_ACTIVE = 4
_BENCH = 5
_HAND = 2
_DISCARD = 3
_DECK = 1

# --- OptionType 定数 ---
_OPT_PLAY = 7
_OPT_ATTACK = 13
_OPT_YES = 1
_OPT_NO = 2


def _resolve_card_id(
    option: Any,
    state: Any,
    your_index: int,
) -> int:
    """選択肢から対象カードIDを解決する。

    Args:
        option: Option オブジェクト。
        state: 現在の State。
        your_index: 自分のプレイヤーインデックス。

    Returns:
        カードID (解決できない場合は 0)。
    """
    # 1. option.cardId が直接指定されている場合
    if option.cardId is not None:
        return option.cardId

    opt_type = option.type
    if hasattr(opt_type, "value"):
        opt_type = opt_type.value

    # 2. PLAY: 手札からプレイ
    if opt_type == _OPT_PLAY and option.index is not None:
        hand = state.players[your_index].hand
        if hand is not None and 0 <= option.index < len(hand):
            return hand[option.index].id
        return 0

    # 3. ATTACK: バトル場ポケモンのID
    if opt_type == _OPT_ATTACK:
        active = state.players[your_index].active
        if active and active[0] is not None:
            return active[0].id
        return 0

    # 4. area/index/playerIndex から特定
    if option.area is not None and option.index is not None:
        area_val = option.area
        if hasattr(area_val, "value"):
            area_val = area_val.value

        player_idx = option.playerIndex
        if player_idx is None:
            player_idx = your_index

        if 0 <= player_idx <= 1:
            player = state.players[player_idx]
            if area_val == _ACTIVE:
                if player.active and player.active[0] is not None:
                    return player.active[0].id
            elif area_val == _BENCH:
                if 0 <= option.index < len(player.bench):
                    poke = player.bench[option.index]
                    if poke is not None:
                        return poke.id
            elif area_val == _HAND:
                if player.hand and 0 <= option.index < len(player.hand):
                    return player.hand[option.index].id
            elif area_val == _DISCARD:
                if 0 <= option.index < len(player.discard):
                    card = player.discard[option.index]
                    if card is not None:
                        return card.id

    return 0


def _encode_position(
    option: Any,
    your_index: int,
) -> list[float]:
    """選択肢の対象位置を 16次元 1-hot にエンコード。

    位置マッピング:
      0: バトル場(自分)    6: バトル場(相手)
      1-5: ベンチ1-5(自分)  7-11: ベンチ1-5(相手)
      12: 手札  13: トラッシュ  14: デッキ  15: その他/なし
    """
    pos = [0.0] * DIMS.TARGET_POS_DIM

    # inPlayArea/inPlayIndex が優先 (ATTACH, EVOLVE 等の対象先)
    area = option.inPlayArea if option.inPlayArea is not None else option.area
    index = option.inPlayIndex if option.inPlayIndex is not None else option.index

    if area is None:
        pos[15] = 1.0
        return pos

    area_val = area
    if hasattr(area_val, "value"):
        area_val = area_val.value

    player_idx = option.playerIndex
    if player_idx is None:
        player_idx = your_index

    is_own = player_idx == your_index

    if area_val == _ACTIVE:
        pos[0 if is_own else 6] = 1.0
    elif area_val == _BENCH:
        idx = index if index is not None else 0
        idx = min(idx, 4)
        pos[(1 + idx) if is_own else (7 + idx)] = 1.0
    elif area_val == _HAND:
        pos[12] = 1.0
    elif area_val == _DISCARD:
        pos[13] = 1.0
    elif area_val == _DECK:
        pos[14] = 1.0
    else:
        pos[15] = 1.0

    return pos


def _encode_meta(
    option: Any,
    n_max_choice: int,
    attack_map: dict[int, Any] | None,
) -> list[float]:
    """追加メタデータ [8次元] を構築。

    内訳:
      [0]: NUMBER値の正規化
      [1]: count / 6.0 (ダメカン配置数)
      [2]: inPlayIndex / 5.0
      [3]: ワザダメージ期待値 / 300.0
      [4]: 必要エネルギー数 / 5.0
      [5]: YES=1.0 / NO=0.0 / other=0.5
      [6]: specialConditionType / 4.0
      [7]: 予備 (0.0)
    """
    meta = [0.0] * DIMS.META_DIM

    opt_type = option.type
    if hasattr(opt_type, "value"):
        opt_type = opt_type.value

    # [0] NUMBER値
    if option.number is not None and n_max_choice > 0:
        meta[0] = option.number / n_max_choice

    # [1] ダメカン配置数
    if option.count is not None:
        meta[1] = min(option.count / NORM.MAX_DAMAGECOUNT_PLACE, 1.0)

    # [2] ベンチインデックス
    if option.inPlayIndex is not None:
        meta[2] = min(option.inPlayIndex / NORM.MAX_BENCH_INDEX, 1.0)

    # [3-4] ワザ情報
    if option.attackId is not None and attack_map is not None:
        attack = attack_map.get(option.attackId)
        if attack is not None:
            meta[3] = min(getattr(attack, "damage", 0) / NORM.MAX_DAMAGE_FOR_META, 1.0)
            energies = getattr(attack, "energies", [])
            meta[4] = min(len(energies) / NORM.MAX_ENERGY_FOR_META, 1.0)

    # [5] YES/NO識別
    if opt_type == _OPT_YES:
        meta[5] = 1.0
    elif opt_type == _OPT_NO:
        meta[5] = 0.0
    else:
        meta[5] = 0.5

    # [6] 特殊状態タイプ
    if option.specialConditionType is not None:
        sc_val = option.specialConditionType
        if hasattr(sc_val, "value"):
            sc_val = sc_val.value
        meta[6] = sc_val / 4.0

    # [7] 予備
    meta[7] = 0.0

    return meta


def encode_actions(
    options: list[Any],
    obs: Any,
    attack_map: dict[int, Any] | None = None,
) -> dict[str, torch.Tensor | int]:
    """選択肢リストをエンコードする。

    Args:
        options: Option オブジェクトのリスト。
        obs: 現在の Observation。
        attack_map: attackId → Attack のマッピング (None 可)。

    Returns:
        以下のキーを持つ辞書:
          - action_type_ids: [N] LongTensor
          - target_card_ids: [N] LongTensor
          - target_position: [N, 16] FloatTensor
          - meta_features: [N, 8] FloatTensor
          - action_mask: [MAX_OPTIONS] BoolTensor
          - num_valid: int

    Raises:
        AssertionError: 選択肢数が MAX_OPTIONS を超えた場合。
    """
    n = len(options)
    assert (
        n <= DIMS.MAX_OPTIONS
    ), f"選択肢数 {n} が最大値 {DIMS.MAX_OPTIONS} を超えています"

    state = obs.current
    your_index = state.yourIndex if state is not None else 0

    # NUMBER タイプの N_max_choice を安全に計算
    n_max_choice = max([opt.number for opt in options if opt.number is not None] + [1])

    type_ids: list[int] = []
    card_ids: list[int] = []
    positions: list[list[float]] = []
    metas: list[list[float]] = []

    for option in options:
        # アクションタイプ
        opt_type = option.type
        if hasattr(opt_type, "value"):
            opt_type = opt_type.value
        action_type = _OPTION_TO_ACTION_TYPE.get(opt_type, 8)
        type_ids.append(action_type)

        # 対象カードID
        if state is not None:
            card_id = _resolve_card_id(option, state, your_index)
        else:
            card_id = option.cardId if option.cardId is not None else 0
        card_ids.append(card_id)

        # 対象位置
        positions.append(_encode_position(option, your_index))

        # メタデータ
        metas.append(_encode_meta(option, n_max_choice, attack_map))

    # マスク (MAX_OPTIONS 長)
    mask = [False] * DIMS.MAX_OPTIONS
    for i in range(n):
        mask[i] = True

    # MAX_OPTIONS にパディング (ネットワーク入力サイズの統一)
    pad_n = DIMS.MAX_OPTIONS - n
    if pad_n > 0:
        type_ids.extend([0] * pad_n)
        card_ids.extend([0] * pad_n)
        positions.extend([[0.0] * DIMS.TARGET_POS_DIM] * pad_n)
        metas.extend([[0.0] * DIMS.META_DIM] * pad_n)

    return {
        "action_type_ids": torch.tensor(type_ids, dtype=torch.long),
        "target_card_ids": torch.tensor(card_ids, dtype=torch.long),
        "target_position": torch.tensor(positions, dtype=torch.float32),
        "meta_features": torch.tensor(metas, dtype=torch.float32),
        "action_mask": torch.tensor(mask, dtype=torch.bool),
        "num_valid": n,
    }
