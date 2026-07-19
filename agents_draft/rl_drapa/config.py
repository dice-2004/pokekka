"""RL エージェントのハイパーパラメータと定数定義。

仕様書の各章で使用される次元数・正規化分母・学習パラメータを
一元管理し、コード全体の整合性を担保する。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dimensions:
    """ネットワーク次元数の定義。"""

    CARD_EMBED_DIM: int = 32
    SLOT_DIM: int = 64  # d = 64 (Embedding 32 + 非Embedding 32)
    NON_EMBED_DIM: int = 32  # スロットの非Embedding特徴量次元
    HIDDEN_DIM: int = 128  # k = 128 (共有状態ベクトル次元)
    GLOBAL_DIM: int = 210  # グローバル特徴量の総次元
    GLOBAL_SCALAR_DIM: int = 18  # サイド(12) + デッキ(2) + スカラ(4)
    ACTION_RAW_DIM: int = 72  # アクション生特徴量次元
    ACTION_TYPE_EMBED_DIM: int = 16
    TARGET_POS_DIM: int = 16
    META_DIM: int = 8
    BENCH_POOL_DIM: int = 384  # 128 × 3 (Max/Mean/Sum)
    CONCAT_DIM: int = 1152  # 384 + 384 + 128 + 128 + 128
    NUM_CARD_IDS: int = 2101  # 0 = padding, 1-2100 = 実カード
    NUM_ACTION_TYPES: int = 12  # アクション分類数
    MAX_OPTIONS: int = 512  # 最大選択肢数
    MAX_BENCH: int = 5  # ベンチ最大枠数
    NUM_ENERGY_TYPES: int = 12  # COLORLESS(0) 〜 TEAM_ROCKET(11)
    ENERGY_VEC_DIM: int = 16  # 12タイプ + 4パディング
    RULE_BOX_DIM: int = 11  # ルールボックス 1-hot 次元数
    PRIZE_ONEHOT_DIM: int = 6  # サイド枚数 1-hot (1〜6)
    MAX_HAND_PAD: int = 60  # 手札パディング最大長
    MAX_DISCARD_PAD: int = 60  # トラッシュパディング最大長


@dataclass(frozen=True)
class Normalization:
    """正規化の分母定義。"""

    MAX_DAMAGE_COUNTERS: float = 32.0  # 最大HP 320 → ダメカン 32個
    MAX_ENERGY_PER_TYPE: float = 10.0  # タイプ別エネルギー正規化上限
    MAX_RETREAT_COST: float = 4.0  # にげるコスト最大値
    MAX_DECK_COUNT: float = 60.0  # 山札枚数の最大値
    MAX_HAND_COUNT: float = 20.0  # 手札枚数の正規化上限
    MAX_TURN: float = 100.0  # ターン数の正規化上限
    MAX_DAMAGE_FOR_META: float = 300.0  # メタデータのダメージ正規化上限
    MAX_ENERGY_FOR_META: float = 5.0  # メタデータのエネルギー数正規化上限
    MAX_DAMAGECOUNT_PLACE: float = 6.0  # ダメカン配置数の正規化上限
    MAX_BENCH_INDEX: float = 5.0  # ベンチインデックスの正規化上限


@dataclass(frozen=True)
class PPOConfig:
    """PPO ハイパーパラメータ。"""

    gamma: float = 0.997
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.2
    entropy_coeff: float = 0.01
    value_coeff: float = 0.5
    max_grad_norm: float = 0.5
    learning_rate: float = 3e-4
    num_epochs: int = 4
    batch_size: int = 64
    rollout_length: int = 256


@dataclass(frozen=True)
class RewardConfig:
    """報酬設計パラメータ（PBRS）。"""

    match_win: float = 1.0
    match_lose: float = -1.0
    gamma_bomb_self_destruct: float = 0.2  # カースドボム自爆時のペナルティ減衰
    gamma_bomb_normal: float = 1.0  # 通常きぜつ時のペナルティ
    beta_potential: float = 0.05  # ポテンシャル関数のスケール
    ko_bonus: float = 1.5  # きぜつ時の w_i ボーナス
    near_ko_bonus: float = 0.5  # 瀕死 (HP <= 30) 時のボーナス
    near_ko_threshold: int = 30  # 瀕死 HP 閾値
    BOMB_CREATURE_IDS: frozenset[int] = field(
        default_factory=lambda: frozenset({132, 133})
    )


@dataclass(frozen=True)
class SelfPlayConfig:
    """自己対戦パラメータ。"""

    checkpoint_interval: int = 5000
    max_checkpoints: int = 20
    eval_interval: int = 2000
    # カリキュラム学習の対戦相手ウェイト
    phase1_weights: dict[str, float] = field(
        default_factory=lambda: {
            "StarEx": 0.70,
            "DragonBomb": 0.0,
            "IonoBellibolt": 0.20,
            "Random": 0.10,
        }
    )
    phase2_weights: dict[str, float] = field(
        default_factory=lambda: {
            "StarEx": 0.40,
            "DragonBomb": 0.30,
            "IonoBellibolt": 0.20,
            "Random": 0.10,
        }
    )
    phase1_to_2_episode: int = 100_000
    phase1_to_2_early_episode: int = 20_000
    phase1_to_2_winrate: float = 0.35
    phase2_to_3_episode: int = 300_000
    phase2_to_3_early_episode: int = 100_000
    phase2_to_3_winrate: float = 0.55


@dataclass(frozen=True)
class ILConfig:
    """模倣学習パラメータ。"""

    lambda_kl: float = 0.1
    lambda_bc: float = 0.01


# --- シングルトンインスタンス ---
DIMS = Dimensions()
NORM = Normalization()
PPO = PPOConfig()
REWARD = RewardConfig()
SELF_PLAY = SelfPlayConfig()
IL = ILConfig()
