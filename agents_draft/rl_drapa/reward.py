"""PBRS 報酬関数モジュール。

仕様書5章に基づく Potential-Based Reward Shaping の実装:
- 勝敗報酬 R_match (+1.0 / -1.0)
- サイド差変化報酬 R_side_diff_adjusted (カースドボム自爆検出付き)
- ポテンシャル差分 gamma × Φ(s') - Φ(s)

Ng et al. (1999) の理論に従い、Φ(s) は純粋に相手盤面の
ダメカン分布のみの関数として定義し、最適ポリシーの不偏性を保証する。
"""

from typing import Any

try:
    from .config import REWARD
except ImportError:
    from config import REWARD  # type: ignore[no-redef]


# --- LogType / AreaType の定数値 (cg.api から直接参照できない場合の安全策) ---
_LOGTYPE_MOVE_CARD = 6
_LOGTYPE_HP_CHANGE = 16
_LOGTYPE_RESULT = 23  # LogType.RESULT
_AREATYPE_DISCARD = 3  # AreaType.DISCARD
_AREATYPE_ACTIVE = 4  # AreaType.ACTIVE
_AREATYPE_BENCH = 5  # AreaType.BENCH


class RewardCalculator:
    """PBRS に基づく報酬計算器。

    エピソード開始時に reset() を呼び出し、各ステップで
    calculate(obs) を呼ぶことで報酬を逐次的に計算する。
    """

    def __init__(
        self,
        your_index: int,
        gamma: float = 0.997,  # PBRS の gamma は PPO の割引率と一致させる
        beta: float = REWARD.beta_potential,
        bomb_ids: frozenset[int] | None = None,
        ko_bonus: float = REWARD.ko_bonus,
        near_ko_bonus: float = REWARD.near_ko_bonus,
        near_ko_threshold: int = REWARD.near_ko_threshold,
        gamma_bomb_self: float = REWARD.gamma_bomb_self_destruct,
        gamma_bomb_normal: float = REWARD.gamma_bomb_normal,
        match_win: float = REWARD.match_win,
        match_lose: float = REWARD.match_lose,
    ) -> None:
        """報酬計算器を初期化。

        Args:
            your_index: 自分のプレイヤーインデックス (0 or 1)。
            gamma: 割引率 (PPO の gamma と同値)。
            beta: ポテンシャル関数のスケール係数。
            bomb_ids: カースドボム自爆対象のカードID集合。
            ko_bonus: きぜつ時の w_i ボーナス。
            near_ko_bonus: 瀕死時の w_i ボーナス。
            near_ko_threshold: 瀕死 HP 閾値。
            gamma_bomb_self: 自爆時のサイドペナルティ減衰率。
            gamma_bomb_normal: 通常時のサイドペナルティ率。
            match_win: 勝利報酬。
            match_lose: 敗北報酬。
        """
        self.your_index = your_index
        self.opp_index = 1 - your_index
        self.gamma = gamma
        self.beta = beta
        self.bomb_ids = bomb_ids or REWARD.BOMB_CREATURE_IDS
        self.ko_bonus = ko_bonus
        self.near_ko_bonus = near_ko_bonus
        self.near_ko_threshold = near_ko_threshold
        self.gamma_bomb_self = gamma_bomb_self
        self.gamma_bomb_normal = gamma_bomb_normal
        self.match_win = match_win
        self.match_lose = match_lose

        # ステートフルな前回値
        self.prev_potential: float = 0.0
        self.prev_own_prize: int = 6
        self.prev_opp_prize: int = 6

    def calculate(self, obs: Any) -> tuple[float, bool]:
        """報酬を計算する。

        Args:
            obs: cg.api.Observation オブジェクト。

        Returns:
            (reward, done) のタプル。
              reward: このステップの報酬。
              done: ゲームが終了したか。
        """
        state = obs.current
        if state is None:
            return 0.0, False

        reward = 0.0
        done = False

        # --- 1. 勝敗報酬 R_match ---
        for log in obs.logs:
            log_type = log.type
            if hasattr(log_type, "value"):
                log_type = log_type.value

            if log_type == _LOGTYPE_RESULT:
                done = True
                if log.result == self.your_index:
                    reward += self.match_win
                elif log.result == self.opp_index:
                    reward += self.match_lose
                # 引き分け (result == 2): reward += 0

        # --- 2. サイド差変化報酬 R_side_diff_adjusted ---
        own_prize = len(state.players[self.your_index].prize)
        opp_prize = len(state.players[self.opp_index].prize)

        # 相手から取ったサイド数 (正値 = 有利)
        delta_opp_taken = self.prev_opp_prize - opp_prize
        # 相手に取られたサイド数 (正値 = 不利)
        delta_own_taken = self.prev_own_prize - own_prize

        bomb_detected = self._detect_bomb_suicide(obs.logs)
        gamma_bomb = self.gamma_bomb_self if bomb_detected else self.gamma_bomb_normal

        reward += delta_opp_taken - gamma_bomb * delta_own_taken

        # --- 3. PBRS ポテンシャル差分 ---
        if done:
            # 終端状態のポテンシャルは 0 (PBRS 理論の要件)
            current_potential = 0.0
        else:
            current_potential = self._compute_potential(state)

        pbrs = self.gamma * current_potential - self.prev_potential
        reward += pbrs

        # --- 状態更新 ---
        self.prev_potential = current_potential
        self.prev_own_prize = own_prize
        self.prev_opp_prize = opp_prize

        return reward, done

    def _compute_potential(self, state: Any) -> float:
        """ポテンシャル関数 Φ(s) を計算。

        Φ(s) = β × Σ_{i ∈ Opponent_Field} w_i × DamageCounters_i

        相手の盤面（バトル場 + ベンチ）の全ポケモンについて、
        ダメカン数と重み付きの加重和を算出する。
        """
        total = 0.0
        opp = state.players[self.opp_index]

        # バトル場
        for poke in opp.active:
            if poke is not None and poke.maxHp > 0:
                damage_counters = (poke.maxHp - poke.hp) / 10.0
                w = 1.0 + self._ko_weight(poke)
                total += w * damage_counters

        # ベンチ
        for poke in opp.bench:
            if poke is not None and poke.maxHp > 0:
                damage_counters = (poke.maxHp - poke.hp) / 10.0
                w = 1.0 + self._ko_weight(poke)
                total += w * damage_counters

        return self.beta * total

    def _ko_weight(self, poke: Any) -> float:
        """きぜつ/瀕死ボーナスの重み w_i を計算。

        - hp <= 0: きぜつ直前 → ko_bonus (1.5)
        - hp <= near_ko_threshold (30): 瀕死 → near_ko_bonus (0.5)
        - それ以外: 0.0
        """
        if poke.hp <= 0:
            return self.ko_bonus
        elif poke.hp <= self.near_ko_threshold:
            return self.near_ko_bonus
        return 0.0

    def _detect_bomb_suicide(self, logs: list[Any]) -> bool:
        """ログからカースドボム自爆を検出。

        同一ターン内で以下の両方が発生した場合に自爆と判定:
        1. BOMB_CREATURE_IDS のカードが自分の場から DISCARD に移動
        2. 相手に HP_CHANGE (putDamageCounter=True) が発生
        """
        bomb_discarded = False
        opp_damaged = False

        for log in logs:
            log_type = log.type
            if hasattr(log_type, "value"):
                log_type = log_type.value

            if (
                log_type == _LOGTYPE_MOVE_CARD
                and log.playerIndex == self.your_index
                and log.cardId is not None
                and log.cardId in self.bomb_ids
            ):
                # fromArea がバトル場またはベンチであることを確認
                # (手札やデッキからの廃棄を誤検出しないようにする)
                from_area = log.fromArea
                if hasattr(from_area, "value"):
                    from_area = from_area.value
                to_area = log.toArea
                if hasattr(to_area, "value"):
                    to_area = to_area.value
                if to_area == _AREATYPE_DISCARD and from_area in (
                    _AREATYPE_ACTIVE,
                    _AREATYPE_BENCH,
                ):
                    bomb_discarded = True

            if (
                log_type == _LOGTYPE_HP_CHANGE
                and log.playerIndex == self.opp_index
                and log.putDamageCounter is True
                and log.value is not None
                and log.value < 0
            ):
                opp_damaged = True

        return bomb_discarded and opp_damaged

    def reset(self) -> None:
        """エピソード開始時に内部状態をリセット。"""
        self.prev_potential = 0.0
        self.prev_own_prize = 6
        self.prev_opp_prize = 6
