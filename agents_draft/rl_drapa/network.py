"""Actor-Critic ニューラルネットワーク（DeepSets + Pointer Network）。

仕様書4章に基づく実装:
- DeepSets方式によるベンチの順不同集約
- Pointer Networkによる可変長アクション空間への対応
- 共有カード埋め込み行列 (2101×32)
- LayerNorm による安定化 (BatchNorm 禁止)
"""

import math

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


class CardEmbedder(nn.Module):
    """共有カード埋め込み行列（2101×32次元）。

    全てのカードIDエンコーディング（フィールド・手札・トラッシュ・
    アクション対象）で単一のインスタンスを共有する。
    """

    def __init__(self, num_ids: int = 2101, embed_dim: int = 32) -> None:
        super().__init__()
        self.embedding = nn.Embedding(num_ids, embed_dim, padding_idx=0)

    def forward(self, card_ids: Tensor) -> Tensor:
        """カードIDを埋め込みベクトルに変換。

        Args:
            card_ids: [...] 任意形状の LongTensor。

        Returns:
            [..., embed_dim] の FloatTensor。
        """
        return self.embedding(card_ids)


class MLPBlock(nn.Module):
    """Linear → LayerNorm → ReLU の基本ブロック。"""

    def __init__(self, in_dim: int, out_dim: int) -> None:
        super().__init__()
        self.linear = nn.Linear(in_dim, out_dim)
        self.norm = nn.LayerNorm(out_dim)

    def forward(self, x: Tensor) -> Tensor:
        """順伝播。"""
        return F.relu(self.norm(self.linear(x)))


class BenchEncoder(nn.Module):
    """ベンチスロットを MLP 処理しマスク付き Max/Mean/Sum Pool で集約。

    自分・相手のベンチで共有される。出力は hidden_dim×3 = 384 次元。
    """

    def __init__(self, slot_dim: int = 64, hidden_dim: int = 128) -> None:
        super().__init__()
        self.slot_mlp = MLPBlock(slot_dim, hidden_dim)
        self.hidden_dim = hidden_dim

    def forward(self, slot_features: Tensor, mask: Tensor) -> Tensor:
        """マスク付き DeepSets 集約。

        Args:
            slot_features: [B, 5, 64] スロット特徴量。
            mask: [B, 5] 有効マスク (1.0=有効, 0.0=空)。

        Returns:
            [B, 384] Max/Mean/Sum の結合ベクトル。
        """
        h = self.slot_mlp(slot_features)  # [B, 5, 128]
        mask_expanded = mask.unsqueeze(-1)  # [B, 5, 1]

        # --- Max Pooling (無効スロットを -1e9 でマスク) ---
        h_for_max = h.masked_fill(mask_expanded == 0, -1e9)
        max_pool = h_for_max.max(dim=1).values  # [B, 128]
        # 全スロットが無効の場合のガード
        all_invalid = mask.sum(dim=1, keepdim=True) == 0  # [B, 1]
        max_pool = max_pool.masked_fill(all_invalid, 0.0)

        # --- Mean Pooling (有効スロットの平均) ---
        h_masked = h * mask_expanded
        valid_count = mask.sum(dim=1, keepdim=True).clamp(min=1.0)  # [B, 1]
        mean_pool = h_masked.sum(dim=1) / valid_count  # [B, 128]

        # --- Sum Pooling ---
        sum_pool = h_masked.sum(dim=1)  # [B, 128]

        return torch.cat([max_pool, mean_pool, sum_pool], dim=-1)  # [B, 384]


class GlobalEncoder(nn.Module):
    """グローバル特徴量エンコーダー (210次元)。

    手札・自トラッシュ・相手トラッシュの Embedding Mean+Sum Pooling
    (各64次元×3 = 192次元) とスカラ特徴量 (18次元) を結合する。
    """

    def __init__(
        self,
        card_embedder: CardEmbedder,
        embed_dim: int = 32,
        scalar_dim: int = 18,
    ) -> None:
        super().__init__()
        self.card_embedder = card_embedder
        self.embed_dim = embed_dim
        self.scalar_dim = scalar_dim

    def _masked_pool(self, card_ids: Tensor, mask: Tensor) -> Tensor:
        """マスク付き Mean+Sum Pooling で 64次元を返す。

        Args:
            card_ids: [B, L] カードID。
            mask: [B, L] 有効マスク。

        Returns:
            [B, 64] Mean(32) + Sum(32) の結合。
        """
        embeds = self.card_embedder(card_ids)  # [B, L, 32]
        mask_exp = mask.unsqueeze(-1)  # [B, L, 1]
        masked = embeds * mask_exp
        valid_count = mask.sum(dim=1, keepdim=True).clamp(min=1.0)  # [B, 1]
        mean_vec = masked.sum(dim=1) / valid_count  # [B, 32]
        sum_vec = masked.sum(dim=1)  # [B, 32]
        return torch.cat([mean_vec, sum_vec], dim=-1)  # [B, 64]

    def forward(
        self,
        own_hand_ids: Tensor,
        own_hand_mask: Tensor,
        own_discard_ids: Tensor,
        own_discard_mask: Tensor,
        opp_discard_ids: Tensor,
        opp_discard_mask: Tensor,
        global_scalars: Tensor,
    ) -> Tensor:
        """グローバル特徴量を構築。

        Returns:
            [B, 210] のテンソル。
        """
        hand_pool = self._masked_pool(own_hand_ids, own_hand_mask)
        own_disc = self._masked_pool(own_discard_ids, own_discard_mask)
        opp_disc = self._masked_pool(opp_discard_ids, opp_discard_mask)
        return torch.cat(
            [hand_pool, own_disc, opp_disc, global_scalars], dim=-1
        )  # [B, 210]


class StateEncoder(nn.Module):
    """構造化テンソル → 共有状態ベクトル s (128次元)。

    アーキテクチャ:
      1. スロット構築: CardEmbedder(32) + 非Embedding(32) = 64次元
      2. ベンチ: 共有MLP(64→128) → マスク付き Max/Mean/Sum Pool → 384次元
      3. バトル場: MLP(64→128)
      4. グローバル: GlobalEncoder(210) → MLP(210→128)
      5. 統合: Concat(1152) → MLP(1152→128→128) = 共有状態ベクトル s
    """

    def __init__(
        self,
        card_embedder: CardEmbedder,
        slot_dim: int = 64,
        hidden_dim: int = 128,
        global_dim: int = 210,
    ) -> None:
        super().__init__()
        self.card_embedder = card_embedder

        # ベンチエンコーダー（自分と相手で重み共有）
        self.bench_encoder = BenchEncoder(slot_dim, hidden_dim)

        # バトル場 MLP
        self.active_mlp = MLPBlock(slot_dim, hidden_dim)

        # グローバルエンコーダー
        self.global_encoder = GlobalEncoder(card_embedder)
        self.global_mlp = MLPBlock(global_dim, hidden_dim)

        # 統合 MLP: 1152 → 128
        concat_dim = hidden_dim * 3 * 2 + hidden_dim * 3  # 384+384+128+128+128=1152
        self.integration = nn.Sequential(
            MLPBlock(concat_dim, hidden_dim),
            MLPBlock(hidden_dim, hidden_dim),
        )

    def _build_slot(self, card_ids: Tensor, features: Tensor) -> Tensor:
        """カードID の Embedding と非Embedding 特徴量を結合して 64次元に。

        Args:
            card_ids: [...] カードID (LongTensor)。
            features: [..., 32] 非Embedding 特徴量。

        Returns:
            [..., 64] のテンソル。
        """
        card_embed = self.card_embedder(card_ids)  # [..., 32]
        return torch.cat([card_embed, features], dim=-1)  # [..., 64]

    def forward(self, state_dict: dict[str, Tensor]) -> Tensor:
        """構造化テンソル辞書から共有状態ベクトルを生成。

        Args:
            state_dict: encode_state() の出力辞書。

        Returns:
            [B, 128] の共有状態ベクトル s。
        """
        # --- スロット構築 (Embedding + 非Embedding) ---
        own_active = self._build_slot(
            state_dict["own_active_card_ids"],
            state_dict["own_active_features"],
        )  # [B, 1, 64]
        opp_active = self._build_slot(
            state_dict["opponent_active_card_ids"],
            state_dict["opponent_active_features"],
        )

        own_bench = self._build_slot(
            state_dict["own_bench_card_ids"],
            state_dict["own_bench_features"],
        )  # [B, 5, 64]
        opp_bench = self._build_slot(
            state_dict["opponent_bench_card_ids"],
            state_dict["opponent_bench_features"],
        )

        # --- バトル場 → MLP (128次元) ---
        # squeeze: [B, 1, 64] → [B, 64]
        own_active_squeezed = own_active.squeeze(-2)
        opp_active_squeezed = opp_active.squeeze(-2)
        own_active_vec = self.active_mlp(own_active_squeezed)  # [B, 128]
        opp_active_vec = self.active_mlp(opp_active_squeezed)

        # --- ベンチ → DeepSets Pool (384次元) ---
        own_bench_vec = self.bench_encoder(
            own_bench, state_dict["bench_mask_own"]
        )  # [B, 384]
        opp_bench_vec = self.bench_encoder(opp_bench, state_dict["bench_mask_opp"])

        # --- グローバル → MLP (128次元) ---
        global_feat = self.global_encoder(
            state_dict["own_hand_card_ids"],
            state_dict["own_hand_mask"],
            state_dict["own_discard_card_ids"],
            state_dict["own_discard_mask"],
            state_dict["opponent_discard_card_ids"],
            state_dict["opponent_discard_mask"],
            state_dict["global_scalars"],
        )  # [B, 210]
        global_vec = self.global_mlp(global_feat)  # [B, 128]

        # --- 統合: 384+384+128+128+128 = 1152 → 128 ---
        concat = torch.cat(
            [
                own_bench_vec,
                opp_bench_vec,
                own_active_vec,
                opp_active_vec,
                global_vec,
            ],
            dim=-1,
        )  # [B, 1152]

        return self.integration(concat)  # [B, 128]


class ActionEncoderNet(nn.Module):
    """アクション特徴量 → k次元アクションベクトル。

    入力 72次元 (ActionType 16 + CardEmbed 32 + Position 16 + Meta 8) を
    MLP で 128次元にマッピングする。
    """

    def __init__(
        self,
        card_embedder: CardEmbedder,
        num_action_types: int = 12,
        action_type_dim: int = 16,
        card_embed_dim: int = 32,
        target_pos_dim: int = 16,
        meta_dim: int = 8,
        hidden_dim: int = 128,
    ) -> None:
        super().__init__()
        self.action_type_embed = nn.Embedding(num_action_types, action_type_dim)
        self.card_embedder = card_embedder  # 共有
        raw_dim = action_type_dim + card_embed_dim + target_pos_dim + meta_dim
        self.mlp = nn.Sequential(
            MLPBlock(raw_dim, hidden_dim),
            MLPBlock(hidden_dim, hidden_dim),
        )

    def forward(
        self,
        action_type_ids: Tensor,
        target_card_ids: Tensor,
        target_position: Tensor,
        meta_features: Tensor,
    ) -> Tensor:
        """アクション特徴量を 128次元に変換。

        Args:
            action_type_ids: [B, N] アクションタイプID。
            target_card_ids: [B, N] 対象カードID。
            target_position: [B, N, 16] 位置 1-hot。
            meta_features: [B, N, 8] メタデータ。

        Returns:
            [B, N, 128] のアクションベクトル。
        """
        type_embed = self.action_type_embed(action_type_ids)  # [B, N, 16]
        card_embed = self.card_embedder(target_card_ids)  # [B, N, 32]
        raw = torch.cat(
            [type_embed, card_embed, target_position, meta_features], dim=-1
        )  # [B, N, 72]
        return self.mlp(raw)  # [B, N, 128]


class PointerNetwork(nn.Module):
    """Dot-product アテンションによるアクションスコアリング。

    query(状態) と key(アクション) の内積 / √d でスコアを算出し、
    無効なアクションをマスクする。
    """

    def __init__(self, hidden_dim: int = 128) -> None:
        super().__init__()
        self.query_proj = nn.Linear(hidden_dim, hidden_dim)
        self.key_proj = nn.Linear(hidden_dim, hidden_dim)
        self.temperature = math.sqrt(hidden_dim)

    def forward(
        self,
        state_vec: Tensor,
        action_vecs: Tensor,
        action_mask: Tensor,
    ) -> Tensor:
        """アクションスコアを計算。

        Args:
            state_vec: [B, 128] 共有状態ベクトル。
            action_vecs: [B, N, 128] アクションベクトル。
            action_mask: [B, N] 有効マスク (True=有効)。

        Returns:
            [B, N] のスコア (logits)。
        """
        query = self.query_proj(state_vec)  # [B, 128]
        keys = self.key_proj(action_vecs)  # [B, N, 128]
        # dot-product: [B, N, 128] × [B, 128, 1] → [B, N]
        logits = torch.bmm(keys, query.unsqueeze(-1)).squeeze(-1)
        logits = logits / self.temperature
        logits = logits.masked_fill(~action_mask, -1e9)
        return logits


class CriticHead(nn.Module):
    """価値関数ヘッド（独立 MLP）。

    共有状態ベクトル s(128) から V(s) をスカラで出力する。
    損失関数には Huber Loss (nn.SmoothL1Loss) を使用する。
    """

    def __init__(self, hidden_dim: int = 128) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, state_vec: Tensor) -> Tensor:
        """価値を推定。

        Args:
            state_vec: [B, 128] 共有状態ベクトル。

        Returns:
            [B, 1] のスカラ価値。
        """
        return self.net(state_vec)


class ActorCritic(nn.Module):
    """統合 Actor-Critic モデル。

    構成:
      - CardEmbedder: 共有カード埋め込み (2101×32)
      - StateEncoder: 構造化テンソル → 共有状態ベクトル s (128)
      - ActionEncoderNet: アクション特徴量 → アクションベクトル (128)
      - PointerNetwork: dot-product アテンション → logits
      - CriticHead: 独立 MLP → V(s)
    """

    def __init__(
        self,
        num_card_ids: int = 2101,
        card_embed_dim: int = 32,
        hidden_dim: int = 128,
    ) -> None:
        super().__init__()
        self.card_embedder = CardEmbedder(num_card_ids, card_embed_dim)
        self.state_encoder = StateEncoder(self.card_embedder)
        self.action_encoder = ActionEncoderNet(self.card_embedder)
        self.pointer = PointerNetwork(hidden_dim)
        self.critic = CriticHead(hidden_dim)

    def forward(
        self,
        state_dict: dict[str, Tensor],
        action_type_ids: Tensor,
        target_card_ids: Tensor,
        target_position: Tensor,
        meta_features: Tensor,
        action_mask: Tensor,
    ) -> tuple[Tensor, Tensor]:
        """順伝播。

        Returns:
            (logits [B, N], value [B, 1]) のタプル。
        """
        state_vec = self.state_encoder(state_dict)  # [B, 128]
        action_vecs = self.action_encoder(
            action_type_ids, target_card_ids, target_position, meta_features
        )  # [B, N, 128]
        logits = self.pointer(state_vec, action_vecs, action_mask)  # [B, N]
        value = self.critic(state_vec)  # [B, 1]
        return logits, value

    def get_action_and_value(
        self,
        state_dict: dict[str, Tensor],
        action_type_ids: Tensor,
        target_card_ids: Tensor,
        target_position: Tensor,
        meta_features: Tensor,
        action_mask: Tensor,
        deterministic: bool = False,
    ) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        """推論時のアクション選択。

        Args:
            deterministic: True の場合 argmax、False の場合サンプリング。

        Returns:
            (action_idx, log_prob, entropy, value) のタプル。
        """
        logits, value = self.forward(
            state_dict,
            action_type_ids,
            target_card_ids,
            target_position,
            meta_features,
            action_mask,
        )
        probs = F.softmax(logits, dim=-1)
        dist = torch.distributions.Categorical(probs=probs)

        if deterministic:
            action = logits.argmax(dim=-1)
        else:
            action = dist.sample()

        log_prob = dist.log_prob(action)
        entropy = dist.entropy()
        return action, log_prob, entropy, value.squeeze(-1)

    def evaluate_actions(
        self,
        state_dict: dict[str, Tensor],
        action_type_ids: Tensor,
        target_card_ids: Tensor,
        target_position: Tensor,
        meta_features: Tensor,
        action_mask: Tensor,
        actions: Tensor,
    ) -> tuple[Tensor, Tensor, Tensor]:
        """学習時のアクション評価。

        既に選択されたアクションに対する log_prob、entropy、value を返す。

        Returns:
            (log_prob, entropy, value) のタプル。
        """
        logits, value = self.forward(
            state_dict,
            action_type_ids,
            target_card_ids,
            target_position,
            meta_features,
            action_mask,
        )
        probs = F.softmax(logits, dim=-1)
        dist = torch.distributions.Categorical(probs=probs)
        log_prob = dist.log_prob(actions)
        entropy = dist.entropy()
        return log_prob, entropy, value.squeeze(-1)
