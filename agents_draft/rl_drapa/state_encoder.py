"""状態エンコーダー: Observation → 構造化テンソル辞書。

仕様書3章に基づき、ゲーム状態を以下の構造化テンソルに変換する:
- フィールドスロット特徴量 (d=64次元 = Embedding 32 + 非Embedding 32)
- グローバル特徴量 (210次元 = Embedding Pooling 192 + スカラ 18)
- マスク情報 (ベンチ有効マスク・手札マスク等)
"""

from collections import Counter
from typing import Any

import torch

try:
    from .config import DIMS, NORM
except ImportError:
    from config import DIMS, NORM  # type: ignore[no-redef]


def _encode_pokemon_features(
    pokemon: Any,
    is_active: bool,
    player_state: Any,
    card_data_map: dict[int, Any],
) -> tuple[int, list[float]]:
    """ポケモン1体の特徴量を抽出する。

    Args:
        pokemon: Pokemon オブジェクト (None の場合はゼロ埋め)。
        is_active: バトル場のポケモンか否か。
        player_state: 所属する PlayerState (特殊状態の判定用)。
        card_data_map: CardID → CardData のマッピング。

    Returns:
        (card_id, 32次元の非Embedding特徴量リスト) のタプル。
    """
    if pokemon is None:
        return 0, [0.0] * DIMS.NON_EMBED_DIM

    card_id: int = pokemon.id
    features: list[float] = []

    # --- Remaining_HP (1次元): hp / maxHp ---
    max_hp = pokemon.maxHp if pokemon.maxHp > 0 else 1
    features.append(pokemon.hp / max_hp)

    # --- Damage_Counters (1次元): ダメカン個数 / 32 ---
    damage_counters = (pokemon.maxHp - pokemon.hp) / 10.0
    features.append(min(damage_counters / NORM.MAX_DAMAGE_COUNTERS, 1.0))

    # --- Energy_Amount (16次元): タイプ別カウント / 10、クリップ ---
    energy_counts = Counter(pokemon.energies)
    energy_vec: list[float] = []
    for etype in range(DIMS.NUM_ENERGY_TYPES):
        count = energy_counts.get(etype, 0)
        energy_vec.append(min(count / NORM.MAX_ENERGY_PER_TYPE, 1.0))
    # 残り4次元はパディング (将来のタイプ追加用)
    energy_vec.extend([0.0] * (DIMS.ENERGY_VEC_DIM - DIMS.NUM_ENERGY_TYPES))
    features.extend(energy_vec)

    # --- Is_Active (1次元) ---
    features.append(1.0 if is_active else 0.0)

    # --- Special_Condition_Flag (1次元): バトル場のみ有効 ---
    if is_active and player_state is not None:
        has_condition = any(
            [
                getattr(player_state, "poisoned", False),
                getattr(player_state, "burned", False),
                getattr(player_state, "asleep", False),
                getattr(player_state, "paralyzed", False),
                getattr(player_state, "confused", False),
            ]
        )
        features.append(1.0 if has_condition else 0.0)
    else:
        features.append(0.0)

    # --- Retreat_Cost (1次元): retreatCost / 4.0 ---
    card_data = card_data_map.get(card_id)
    if card_data is not None:
        retreat = getattr(card_data, "retreatCost", 0) or 0
        features.append(min(retreat / NORM.MAX_RETREAT_COST, 1.0))
    else:
        features.append(0.0)

    # --- Rule_Box_Flag (11次元の 1-hot) ---
    rule_box = [0.0] * DIMS.RULE_BOX_DIM
    if card_data is not None:
        if getattr(card_data, "ex", False):
            rule_box[1] = 1.0  # ex
        elif getattr(card_data, "tera", False):
            rule_box[9] = 1.0  # テラスタル
        else:
            rule_box[0] = 1.0  # なし (一般ポケモン)
    else:
        rule_box[0] = 1.0
    features.extend(rule_box)

    assert len(features) == DIMS.NON_EMBED_DIM, (
        f"非Embedding特徴量は{DIMS.NON_EMBED_DIM}次元であるべきだが"
        f"、{len(features)}次元になっている"
    )
    return card_id, features


def _encode_field_slots(
    player_state: Any,
    card_data_map: dict[int, Any],
) -> tuple[
    torch.Tensor,
    torch.Tensor,
    torch.Tensor,
    torch.Tensor,
    torch.Tensor,
]:
    """プレイヤーのバトル場+ベンチをエンコード。

    Returns:
        (active_card_ids[1], active_features[1,32],
         bench_card_ids[5], bench_features[5,32], bench_mask[5])
    """
    # --- バトル場 (1枠) ---
    if player_state.active and player_state.active[0] is not None:
        active_poke = player_state.active[0]
        a_id, a_feat = _encode_pokemon_features(
            active_poke, True, player_state, card_data_map
        )
    else:
        a_id, a_feat = 0, [0.0] * DIMS.NON_EMBED_DIM

    active_card_ids = torch.tensor([a_id], dtype=torch.long)
    active_features = torch.tensor([a_feat], dtype=torch.float32)

    # --- ベンチ (最大5枠) ---
    bench_ids: list[int] = []
    bench_feats: list[list[float]] = []
    bench_mask: list[float] = []

    for i in range(DIMS.MAX_BENCH):
        if i < len(player_state.bench) and player_state.bench[i] is not None:
            b_id, b_feat = _encode_pokemon_features(
                player_state.bench[i], False, player_state, card_data_map
            )
            bench_ids.append(b_id)
            bench_feats.append(b_feat)
            bench_mask.append(1.0)
        else:
            bench_ids.append(0)
            bench_feats.append([0.0] * DIMS.NON_EMBED_DIM)
            bench_mask.append(0.0)

    bench_card_ids = torch.tensor(bench_ids, dtype=torch.long)
    bench_features = torch.tensor(bench_feats, dtype=torch.float32)
    bench_mask_tensor = torch.tensor(bench_mask, dtype=torch.float32)

    return (
        active_card_ids,
        active_features,
        bench_card_ids,
        bench_features,
        bench_mask_tensor,
    )


def _encode_card_id_list(
    cards: list[Any] | None,
    max_len: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    """カードIDリストをパディング付きテンソルに変換。

    Args:
        cards: Card オブジェクトのリスト (None の場合は空リスト扱い)。
        max_len: パディング後の長さ。

    Returns:
        (card_ids[max_len], mask[max_len])
    """
    if cards is None:
        cards = []

    ids: list[int] = []
    mask: list[float] = []

    for i in range(max_len):
        if i < len(cards) and cards[i] is not None:
            ids.append(cards[i].id)
            mask.append(1.0)
        else:
            ids.append(0)
            mask.append(0.0)

    return (
        torch.tensor(ids, dtype=torch.long),
        torch.tensor(mask, dtype=torch.float32),
    )


def _encode_global_scalars(
    own_player: Any,
    opp_player: Any,
    state: Any,
) -> torch.Tensor:
    """グローバルスカラ特徴量 [18次元] を構築。

    内訳:
      own_prize_1hot (6) + opponent_prize_1hot (6)
      + own_deck_count (1) + opponent_deck_count (1)
      + opponent_hand_count (1)
      + Is_First_Player (1) + support_played (1) + Current_Turn (1)
    """
    scalars: list[float] = []

    # --- 自分のサイド 1-hot (6次元) ---
    own_prize_count = len(own_player.prize) if own_player.prize else 0
    own_prize_1hot = [0.0] * DIMS.PRIZE_ONEHOT_DIM
    if 1 <= own_prize_count <= DIMS.PRIZE_ONEHOT_DIM:
        own_prize_1hot[own_prize_count - 1] = 1.0
    scalars.extend(own_prize_1hot)

    # --- 相手のサイド 1-hot (6次元) ---
    opp_prize_count = len(opp_player.prize) if opp_player.prize else 0
    opp_prize_1hot = [0.0] * DIMS.PRIZE_ONEHOT_DIM
    if 1 <= opp_prize_count <= DIMS.PRIZE_ONEHOT_DIM:
        opp_prize_1hot[opp_prize_count - 1] = 1.0
    scalars.extend(opp_prize_1hot)

    # --- 山札枚数 (各1次元) ---
    scalars.append(own_player.deckCount / NORM.MAX_DECK_COUNT)
    scalars.append(opp_player.deckCount / NORM.MAX_DECK_COUNT)

    # --- 相手手札枚数 (1次元) ---
    scalars.append(min(opp_player.handCount / NORM.MAX_HAND_COUNT, 1.0))

    # --- 先攻フラグ (1次元) ---
    your_index = state.yourIndex
    first_player = state.firstPlayer
    is_first = 1.0 if (first_player >= 0 and your_index == first_player) else 0.0
    scalars.append(is_first)

    # --- サポーター使用済み (1次元) ---
    scalars.append(1.0 if state.supporterPlayed else 0.0)

    # --- 経過ターン数 (1次元) ---
    scalars.append(min(state.turn / NORM.MAX_TURN, 1.0))

    assert len(scalars) == DIMS.GLOBAL_SCALAR_DIM, (
        f"グローバルスカラは{DIMS.GLOBAL_SCALAR_DIM}次元であるべきだが"
        f"、{len(scalars)}次元になっている"
    )
    return torch.tensor(scalars, dtype=torch.float32)


def encode_state(
    obs: Any,
    card_data_map: dict[int, Any],
) -> dict[str, torch.Tensor]:
    """Observation を構造化テンソル辞書に変換するメイン関数。

    Args:
        obs: cg.api.Observation オブジェクト。
        card_data_map: CardID → CardData のマッピング。

    Returns:
        ニューラルネットワーク入力用の構造化テンソル辞書。
    """
    state = obs.current

    # 初回デッキ選択時 (state=None) はゼロテンソルを返す
    if state is None:
        return _make_zero_state_dict()

    your_index: int = state.yourIndex
    opp_index: int = 1 - your_index
    own_player = state.players[your_index]
    opp_player = state.players[opp_index]

    # --- フィールドスロットのエンコード ---
    (
        own_active_ids,
        own_active_feat,
        own_bench_ids,
        own_bench_feat,
        own_bench_mask,
    ) = _encode_field_slots(own_player, card_data_map)

    (
        opp_active_ids,
        opp_active_feat,
        opp_bench_ids,
        opp_bench_feat,
        opp_bench_mask,
    ) = _encode_field_slots(opp_player, card_data_map)

    # --- グローバル特徴量用カードIDリスト ---
    own_hand_ids, own_hand_mask = _encode_card_id_list(
        own_player.hand, DIMS.MAX_HAND_PAD
    )
    own_discard_ids, own_discard_mask = _encode_card_id_list(
        own_player.discard, DIMS.MAX_DISCARD_PAD
    )
    opp_discard_ids, opp_discard_mask = _encode_card_id_list(
        opp_player.discard, DIMS.MAX_DISCARD_PAD
    )

    # --- グローバルスカラ ---
    global_scalars = _encode_global_scalars(own_player, opp_player, state)

    return {
        # カードID (Embedding用)
        "own_active_card_ids": own_active_ids,
        "own_bench_card_ids": own_bench_ids,
        "opponent_active_card_ids": opp_active_ids,
        "opponent_bench_card_ids": opp_bench_ids,
        # 非Embedding特徴量
        "own_active_features": own_active_feat,
        "own_bench_features": own_bench_feat,
        "opponent_active_features": opp_active_feat,
        "opponent_bench_features": opp_bench_feat,
        # グローバル特徴量用カードIDリスト
        "own_hand_card_ids": own_hand_ids,
        "own_discard_card_ids": own_discard_ids,
        "opponent_discard_card_ids": opp_discard_ids,
        # グローバルスカラ
        "global_scalars": global_scalars,
        # マスク
        "bench_mask_own": own_bench_mask,
        "bench_mask_opp": opp_bench_mask,
        "own_hand_mask": own_hand_mask,
        "own_discard_mask": own_discard_mask,
        "opponent_discard_mask": opp_discard_mask,
    }


def _make_zero_state_dict() -> dict[str, torch.Tensor]:
    """初期状態用のゼロテンソル辞書を生成。"""
    return {
        "own_active_card_ids": torch.zeros(1, dtype=torch.long),
        "own_bench_card_ids": torch.zeros(DIMS.MAX_BENCH, dtype=torch.long),
        "opponent_active_card_ids": torch.zeros(1, dtype=torch.long),
        "opponent_bench_card_ids": torch.zeros(DIMS.MAX_BENCH, dtype=torch.long),
        "own_active_features": torch.zeros(1, DIMS.NON_EMBED_DIM),
        "own_bench_features": torch.zeros(DIMS.MAX_BENCH, DIMS.NON_EMBED_DIM),
        "opponent_active_features": torch.zeros(1, DIMS.NON_EMBED_DIM),
        "opponent_bench_features": torch.zeros(DIMS.MAX_BENCH, DIMS.NON_EMBED_DIM),
        "own_hand_card_ids": torch.zeros(DIMS.MAX_HAND_PAD, dtype=torch.long),
        "own_discard_card_ids": torch.zeros(DIMS.MAX_DISCARD_PAD, dtype=torch.long),
        "opponent_discard_card_ids": torch.zeros(
            DIMS.MAX_DISCARD_PAD, dtype=torch.long
        ),
        "global_scalars": torch.zeros(DIMS.GLOBAL_SCALAR_DIM),
        "bench_mask_own": torch.zeros(DIMS.MAX_BENCH),
        "bench_mask_opp": torch.zeros(DIMS.MAX_BENCH),
        "own_hand_mask": torch.zeros(DIMS.MAX_HAND_PAD),
        "own_discard_mask": torch.zeros(DIMS.MAX_DISCARD_PAD),
        "opponent_discard_mask": torch.zeros(DIMS.MAX_DISCARD_PAD),
    }
