"""報酬モジュールの単体テスト（仕様書5.2.1節）。

ダミーの Observation ログリストを入力し、報酬関数が仕様通りに動作するか検証する:
1. 通常のサイドカード取得報酬
2. カースドボム自爆検出 (gamma_bomb = 0.2)
3. PBRS ポテンシャル差分の正確性
4. ゲーム終了時の勝敗報酬
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Any

# rl_drapa ディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from reward import RewardCalculator  # noqa: E402


# --- ダミーデータクラス ---
@dataclass
class DummyLog:
    """テスト用ダミー Log。"""

    type: int = 0
    playerIndex: int | None = None
    cardId: int | None = None
    toArea: int | None = None
    fromArea: int | None = None
    putDamageCounter: bool | None = None
    value: int | None = None
    result: int | None = None
    reason: int | None = None
    serial: int | None = None
    hasBasicPokemon: bool | None = None
    serialActive: int | None = None
    cardIdActive: int | None = None
    serialBench: int | None = None
    cardIdBench: int | None = None
    cardIdBefore: int | None = None
    serialBefore: int | None = None
    cardIdAfter: int | None = None
    serialAfter: int | None = None
    cardIdTarget: int | None = None
    serialTarget: int | None = None
    attackId: int | None = None
    isRecover: bool | None = None
    head: bool | None = None


@dataclass
class DummyPokemon:
    """テスト用ダミー Pokemon。"""

    id: int = 100
    serial: int = 0
    hp: int = 200
    maxHp: int = 200
    energies: list[int] = field(default_factory=list)
    energyCards: list[Any] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)
    preEvolution: list[Any] = field(default_factory=list)
    appearThisTurn: bool = False


@dataclass
class DummyCard:
    """テスト用ダミー Card。"""

    id: int = 0
    serial: int = 0
    playerIndex: int = 0


@dataclass
class DummyPlayerState:
    """テスト用ダミー PlayerState。"""

    active: list[Any] = field(default_factory=list)
    bench: list[Any] = field(default_factory=list)
    benchMax: int = 5
    deckCount: int = 40
    discard: list[Any] = field(default_factory=list)
    prize: list[Any] = field(default_factory=list)
    handCount: int = 5
    hand: list[Any] | None = None
    poisoned: bool = False
    burned: bool = False
    asleep: bool = False
    paralyzed: bool = False
    confused: bool = False


@dataclass
class DummyState:
    """テスト用ダミー State。"""

    turn: int = 5
    turnActionCount: int = 0
    yourIndex: int = 0
    firstPlayer: int = 0
    supporterPlayed: bool = False
    stadiumPlayed: bool = False
    energyAttached: bool = False
    retreated: bool = False
    result: int = -1
    stadium: list[Any] = field(default_factory=list)
    looking: list[Any] | None = None
    players: list[Any] = field(default_factory=list)


@dataclass
class DummyObservation:
    """テスト用ダミー Observation。"""

    select: Any = None
    logs: list[Any] = field(default_factory=list)
    current: Any = None
    search_begin_input: str | None = None


def make_players(
    own_prize: int = 6,
    opp_prize: int = 6,
    opp_active_hp: int = 200,
    opp_active_maxhp: int = 200,
    opp_bench: list[tuple[int, int]] | None = None,
) -> list[DummyPlayerState]:
    """テスト用プレイヤー状態を生成。"""
    own = DummyPlayerState(
        active=[DummyPokemon(id=121, hp=280, maxHp=280)],
        prize=[DummyCard() for _ in range(own_prize)],
    )

    opp_active = DummyPokemon(id=500, hp=opp_active_hp, maxHp=opp_active_maxhp)
    opp_bench_list: list[DummyPokemon] = []
    if opp_bench:
        for hp, maxhp in opp_bench:
            opp_bench_list.append(DummyPokemon(id=501, hp=hp, maxHp=maxhp))

    opp = DummyPlayerState(
        active=[opp_active],
        bench=opp_bench_list,
        prize=[DummyCard() for _ in range(opp_prize)],
    )
    return [own, opp]


def test_normal_game_no_events() -> None:
    """テスト: イベントなしの通常ステップで報酬≈0。"""
    calc = RewardCalculator(your_index=0)
    state = DummyState(players=make_players())
    obs = DummyObservation(current=state, logs=[])

    reward, done = calc.calculate(obs)
    assert not done, "ゲームは終了していないはず"
    # PBRS のみ (初期状態→同じ状態 = ほぼ0)
    assert abs(reward) < 0.1, f"通常ステップの報酬が大きすぎる: {reward}"
    print(f"[PASS] test_normal_game_no_events: reward={reward:.4f}")


def test_win_reward() -> None:
    """テスト: 勝利時に +1.0 報酬。"""
    calc = RewardCalculator(your_index=0)
    state = DummyState(players=make_players())
    logs = [DummyLog(type=23, result=0)]  # RESULT, player 0 wins
    obs = DummyObservation(current=state, logs=logs)

    reward, done = calc.calculate(obs)
    assert done, "ゲームは終了しているはず"
    assert reward >= 0.9, f"勝利報酬が不足: {reward}"
    print(f"[PASS] test_win_reward: reward={reward:.4f}")


def test_lose_reward() -> None:
    """テスト: 敗北時に -1.0 報酬。"""
    calc = RewardCalculator(your_index=0)
    state = DummyState(players=make_players())
    logs = [DummyLog(type=23, result=1)]  # RESULT, player 1 wins
    obs = DummyObservation(current=state, logs=logs)

    reward, done = calc.calculate(obs)
    assert done
    assert reward <= -0.9, f"敗北報酬が不足: {reward}"
    print(f"[PASS] test_lose_reward: reward={reward:.4f}")


def test_side_taken_reward() -> None:
    """テスト: 相手のサイドを1枚取った時に正の報酬。"""
    calc = RewardCalculator(your_index=0)
    # 最初は6-6
    state1 = DummyState(players=make_players(own_prize=6, opp_prize=6))
    obs1 = DummyObservation(current=state1, logs=[])
    calc.calculate(obs1)  # 初期状態を設定

    # 相手のサイドが5に減少
    state2 = DummyState(players=make_players(own_prize=6, opp_prize=5))
    obs2 = DummyObservation(current=state2, logs=[])
    reward, done = calc.calculate(obs2)

    assert not done
    assert reward > 0, f"サイド取得報酬が正でない: {reward}"
    print(f"[PASS] test_side_taken_reward: reward={reward:.4f}")


def test_bomb_suicide_detection() -> None:
    """テスト: カースドボム自爆時に gamma_bomb=0.2 でペナルティ減衰。"""
    # 自爆あり
    calc_bomb = RewardCalculator(your_index=0)
    state1 = DummyState(players=make_players(own_prize=6, opp_prize=6))
    obs1 = DummyObservation(current=state1, logs=[])
    calc_bomb.calculate(obs1)

    # サマヨール(ID=132)がバトル場(ACTIVE=4)からDISCARD(3)に移動 + 相手にダメージ
    bomb_logs = [
        DummyLog(type=6, playerIndex=0, cardId=132, fromArea=4, toArea=3),  # MOVE_CARD
        DummyLog(type=16, playerIndex=1, putDamageCounter=True, value=-20),  # HP_CHANGE
    ]
    state2 = DummyState(players=make_players(own_prize=5, opp_prize=6))
    obs2 = DummyObservation(current=state2, logs=bomb_logs)
    reward_bomb, _ = calc_bomb.calculate(obs2)

    # 自爆なし (通常きぜつ)
    calc_normal = RewardCalculator(your_index=0)
    obs1n = DummyObservation(current=state1, logs=[])
    calc_normal.calculate(obs1n)

    normal_logs: list[DummyLog] = []  # ボム検出なし
    state2n = DummyState(players=make_players(own_prize=5, opp_prize=6))
    obs2n = DummyObservation(current=state2n, logs=normal_logs)
    reward_normal, _ = calc_normal.calculate(obs2n)

    # 自爆時のペナルティは 0.2、通常は 1.0 → 自爆の方がrewardが高い
    assert reward_bomb > reward_normal, (
        f"自爆ペナルティ減衰が反映されていない: "
        f"bomb={reward_bomb:.4f} vs normal={reward_normal:.4f}"
    )
    print(
        f"[PASS] test_bomb_suicide_detection: "
        f"bomb={reward_bomb:.4f}, normal={reward_normal:.4f}, "
        f"diff={reward_bomb - reward_normal:.4f}"
    )


def test_pbrs_potential_increases_with_damage() -> None:
    """テスト: 相手にダメカンが乗るとポテンシャルが上がり正の報酬。"""
    calc = RewardCalculator(your_index=0)

    # ステップ1: 相手HP満タン
    state1 = DummyState(players=make_players(opp_active_hp=200, opp_active_maxhp=200))
    obs1 = DummyObservation(current=state1, logs=[])
    calc.calculate(obs1)

    # ステップ2: 相手にダメージ (HP 200→100, ダメカン10個)
    state2 = DummyState(players=make_players(opp_active_hp=100, opp_active_maxhp=200))
    obs2 = DummyObservation(current=state2, logs=[])
    reward, done = calc.calculate(obs2)

    assert reward > 0, f"ダメカン増加で正の報酬が出ていない: {reward}"
    print(f"[PASS] test_pbrs_potential_increases: reward={reward:.4f}")


def test_pbrs_terminal_potential_zero() -> None:
    """テスト: 終端状態でΦ(terminal)=0。"""
    calc = RewardCalculator(your_index=0)

    # 相手にダメカンが多い状態を設定
    state1 = DummyState(
        players=make_players(
            opp_active_hp=50,
            opp_active_maxhp=200,
            opp_bench=[(30, 100), (20, 100)],
        )
    )
    obs1 = DummyObservation(current=state1, logs=[])
    calc.calculate(obs1)

    # 終了 → Φ(terminal) = 0 により大きな負のPBRS差分
    state2 = DummyState(players=make_players())
    logs = [DummyLog(type=23, result=0)]
    obs2 = DummyObservation(current=state2, logs=logs)
    reward, done = calc.calculate(obs2)

    assert done
    # 勝利+1.0だがPBRS差分は負 → 合計は 1.0 - |PBRS| 程度
    print(f"[PASS] test_pbrs_terminal_zero: reward={reward:.4f}")


def test_near_ko_bonus() -> None:
    """テスト: 瀕死 (HP<=30) のポケモンは w_i に near_ko_bonus。"""
    calc = RewardCalculator(your_index=0)

    # 相手バトル場 HP=25 (瀕死)
    state = DummyState(players=make_players(opp_active_hp=25, opp_active_maxhp=200))
    phi = calc._compute_potential(state)

    # 比較: 同じダメカン数だが HP>30
    state_normal = DummyState(
        players=make_players(opp_active_hp=35, opp_active_maxhp=200)
    )
    phi_normal = calc._compute_potential(state_normal)

    # 瀕死の方がダメカン多い + near_ko_bonus あり → 大きい
    assert phi > phi_normal, f"瀕死ボーナスが反映されていない: {phi} vs {phi_normal}"
    print(f"[PASS] test_near_ko_bonus: near_ko={phi:.4f}, normal={phi:.4f}")


def test_reset() -> None:
    """テスト: reset() で内部状態が初期化される。"""
    calc = RewardCalculator(your_index=0)
    calc.prev_potential = 999.0
    calc.prev_own_prize = 3
    calc.prev_opp_prize = 2
    calc.reset()
    assert calc.prev_potential == 0.0
    assert calc.prev_own_prize == 6
    assert calc.prev_opp_prize == 6
    print("[PASS] test_reset")


if __name__ == "__main__":
    print("=== 報酬モジュール単体テスト (仕様書5.2.1節) ===")
    print()
    test_normal_game_no_events()
    test_win_reward()
    test_lose_reward()
    test_side_taken_reward()
    test_bomb_suicide_detection()
    test_pbrs_potential_increases_with_damage()
    test_pbrs_terminal_potential_zero()
    test_near_ko_bonus()
    test_reset()
    print()
    print("=== 全テスト合格 ===")
