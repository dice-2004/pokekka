"""PPO トレーニングパイプライン。

仕様書2章・5章に基づく学習ループ:
- GAE (Generalized Advantage Estimation) による利点推定
- PPO-Clip アルゴリズムによるポリシー最適化
- Huber Loss による価値関数学習
- エントロピーボーナスによる探索促進
"""

import os
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

try:
    from .config import PPO
    from .network import ActorCritic
except ImportError:
    from config import PPO  # type: ignore[no-redef]
    from network import ActorCritic  # type: ignore[no-redef]


class RolloutBuffer:
    """ロールアウトバッファ。

    PPO 学習用の経験データを蓄積する。各ステップのデータとして
    状態辞書・アクション情報・報酬・価値・log_prob を保存する。
    """

    def __init__(self) -> None:
        """バッファを初期化。"""
        self.state_dicts: list[dict[str, Tensor]] = []
        self.action_type_ids: list[Tensor] = []
        self.target_card_ids: list[Tensor] = []
        self.target_positions: list[Tensor] = []
        self.meta_features: list[Tensor] = []
        self.action_masks: list[Tensor] = []
        self.actions: list[Tensor] = []
        self.log_probs: list[Tensor] = []
        self.rewards: list[float] = []
        self.values: list[Tensor] = []
        self.dones: list[bool] = []

    def add(
        self,
        state_dict: dict[str, Tensor],
        action_type_ids: Tensor,
        target_card_ids: Tensor,
        target_position: Tensor,
        meta_features: Tensor,
        action_mask: Tensor,
        action: Tensor,
        log_prob: Tensor,
        reward: float,
        value: Tensor,
        done: bool,
    ) -> None:
        """ステップデータを追加。"""
        self.state_dicts.append({k: v.detach().cpu() for k, v in state_dict.items()})
        self.action_type_ids.append(action_type_ids.detach().cpu())
        self.target_card_ids.append(target_card_ids.detach().cpu())
        self.target_positions.append(target_position.detach().cpu())
        self.meta_features.append(meta_features.detach().cpu())
        self.action_masks.append(action_mask.detach().cpu())
        self.actions.append(action.detach().cpu())
        self.log_probs.append(log_prob.detach().cpu())
        self.rewards.append(reward)
        self.values.append(value.detach().cpu())
        self.dones.append(done)

    def compute_returns_and_advantages(
        self,
        last_value: float,
        gamma: float = PPO.gamma,
        gae_lambda: float = PPO.gae_lambda,
    ) -> tuple[Tensor, Tensor]:
        """GAE によるリターンとアドバンテージを計算。

        Args:
            last_value: 最後のステップの次の状態の価値推定。
            gamma: 割引率。
            gae_lambda: GAE のラムダ。

        Returns:
            (returns, advantages) のタプル。各 [T] のテンソル。
        """
        t = len(self.rewards)
        advantages = torch.zeros(t)
        returns = torch.zeros(t)

        last_gae = 0.0
        next_value = last_value

        for step in reversed(range(t)):
            if self.dones[step]:
                next_value = 0.0
                last_gae = 0.0

            value = self.values[step].item()
            delta = self.rewards[step] + gamma * next_value - value
            last_gae = delta + gamma * gae_lambda * last_gae
            advantages[step] = last_gae
            returns[step] = advantages[step] + value
            next_value = value

        return returns, advantages

    def clear(self) -> None:
        """バッファをクリア。"""
        self.__init__()  # type: ignore[misc]

    def __len__(self) -> int:
        """バッファ内のステップ数。"""
        return len(self.rewards)


class PPOTrainer:
    """PPO トレーナー。

    ActorCritic モデルを PPO-Clip アルゴリズムで学習する。
    """

    def __init__(
        self,
        model: ActorCritic,
        lr: float = PPO.learning_rate,
        clip_epsilon: float = PPO.clip_epsilon,
        entropy_coeff: float = PPO.entropy_coeff,
        value_coeff: float = PPO.value_coeff,
        max_grad_norm: float = PPO.max_grad_norm,
        num_epochs: int = PPO.num_epochs,
        batch_size: int = PPO.batch_size,
        device: str = "cpu",
        il_model: ActorCritic | None = None,  # 模倣学習済みモデル (逆KL計算用)
    ) -> None:
        """トレーナーを初期化。

        Args:
            model: 学習対象の ActorCritic モデル。
            lr: 学習率。
            clip_epsilon: PPO クリッピング閾値。
            entropy_coeff: エントロピーボーナス係数。
            value_coeff: 価値損失の重み。
            max_grad_norm: 勾配クリッピングの最大ノルム。
            num_epochs: 各アップデートのエポック数。
            batch_size: ミニバッチサイズ。
            device: 使用デバイス (cpu/cuda)。
            il_model: 逆KL正則化のターゲットとする模倣学習済みモデル。
        """
        self.model = model
        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        self.clip_epsilon = clip_epsilon
        self.entropy_coeff = entropy_coeff
        self.value_coeff = value_coeff
        self.max_grad_norm = max_grad_norm
        self.num_epochs = num_epochs
        self.batch_size = batch_size
        self.device = device
        self.value_loss_fn = nn.SmoothL1Loss()  # Huber Loss
        self.il_model = il_model
        if self.il_model is not None:
            self.il_model.eval()  # 評価モードに固定

    def update(
        self,
        buffer: RolloutBuffer,
        last_value: float,
        lambda_kl: float = 0.0,  # 逆KL正則化係数
    ) -> dict[str, float]:
        """バッファの経験データを使って PPO アップデートを実行。

        Args:
            buffer: ロールアウトバッファ。
            last_value: 最後のステップの次の価値。
            lambda_kl: 逆KL正則化の重み。

        Returns:
            学習メトリクス辞書 (policy_loss, value_loss, entropy, kl_div 等)。
        """
        returns, advantages = buffer.compute_returns_and_advantages(last_value)

        # アドバンテージの正規化
        if advantages.std() > 1e-8:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        t = len(buffer)

        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy = 0.0
        total_kl_div = 0.0
        update_count = 0

        for _epoch in range(self.num_epochs):
            # ミニバッチでシャッフル
            perm = torch.randperm(t).tolist()
            for start in range(0, t, self.batch_size):
                end = min(start + self.batch_size, t)
                batch_indices = perm[start:end]

                if len(batch_indices) == 0:
                    continue

                # バッチデータの構築
                batch_state = self._batch_state_dicts(
                    [buffer.state_dicts[i] for i in batch_indices]
                )
                batch_action_type = torch.stack(
                    [buffer.action_type_ids[i] for i in batch_indices]
                ).to(self.device)
                batch_card_ids = torch.stack(
                    [buffer.target_card_ids[i] for i in batch_indices]
                ).to(self.device)
                batch_positions = torch.stack(
                    [buffer.target_positions[i] for i in batch_indices]
                ).to(self.device)
                batch_meta = torch.stack(
                    [buffer.meta_features[i] for i in batch_indices]
                ).to(self.device)
                batch_masks = torch.stack(
                    [buffer.action_masks[i] for i in batch_indices]
                ).to(self.device)
                batch_actions = torch.stack(
                    [buffer.actions[i] for i in batch_indices]
                ).to(self.device)
                batch_old_log_probs = torch.stack(
                    [buffer.log_probs[i] for i in batch_indices]
                ).to(self.device)
                batch_returns = returns[batch_indices].to(self.device)
                batch_advantages = advantages[batch_indices].to(self.device)

                # 評価
                logits_theta, values = self.model.forward(
                    batch_state,
                    batch_action_type,
                    batch_card_ids,
                    batch_positions,
                    batch_meta,
                    batch_masks,
                )
                probs_theta = F.softmax(logits_theta, dim=-1)
                dist_theta = torch.distributions.Categorical(probs=probs_theta)
                new_log_probs = dist_theta.log_prob(batch_actions)
                entropy = dist_theta.entropy()

                # PPO-Clip 損失
                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                surr1 = ratio * batch_advantages
                surr2 = (
                    torch.clamp(
                        ratio,
                        1.0 - self.clip_epsilon,
                        1.0 + self.clip_epsilon,
                    )
                    * batch_advantages
                )
                policy_loss = -torch.min(surr1, surr2).mean()

                # 価値損失 (Huber Loss)
                value_loss = self.value_loss_fn(values.squeeze(-1), batch_returns)

                # エントロピーボーナス
                entropy_loss = -entropy.mean()

                # 統合損失
                loss = (
                    policy_loss
                    + self.value_coeff * value_loss
                    + self.entropy_coeff * entropy_loss
                )

                # 逆KLダイバージェンス正則化の適用: D_KL(pi_theta || pi_IL)
                kl_div_val = 0.0
                if self.il_model is not None and lambda_kl > 0:
                    with torch.no_grad():
                        logits_il, _ = self.il_model.forward(
                            batch_state,
                            batch_action_type,
                            batch_card_ids,
                            batch_positions,
                            batch_meta,
                            batch_masks,
                        )
                        probs_il = F.softmax(logits_il, dim=-1)
                    dist_il = torch.distributions.Categorical(probs=probs_il)
                    kl_div = torch.distributions.kl.kl_divergence(dist_theta, dist_il).mean()
                    loss = loss + lambda_kl * kl_div
                    kl_div_val = kl_div.item()

                # 逆伝播
                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
                self.optimizer.step()

                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                total_entropy += entropy.mean().item()
                total_kl_div += kl_div_val
                update_count += 1

        if update_count == 0:
            update_count = 1

        return {
            "policy_loss": total_policy_loss / update_count,
            "value_loss": total_value_loss / update_count,
            "entropy": total_entropy / update_count,
            "kl_div": total_kl_div / update_count,
        }

    def pretrain_step(
        self,
        batch_state: dict[str, Tensor],
        batch_action_type: Tensor,
        batch_card_ids: Tensor,
        batch_positions: Tensor,
        batch_meta: Tensor,
        batch_masks: Tensor,
        batch_actions: Tensor,
    ) -> float:
        """Behavioral Cloning (IL) による事前学習の1ステップアップデート。

        Returns:
            BC 損失。
        """
        self.model.train()
        logits, _ = self.model.forward(
            batch_state,
            batch_action_type,
            batch_card_ids,
            batch_positions,
            batch_meta,
            batch_masks,
        )
        probs = F.softmax(logits, dim=-1)
        dist = torch.distributions.Categorical(probs=probs)
        log_prob = dist.log_prob(batch_actions)
        loss = -log_prob.mean()

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
        self.optimizer.step()

        return loss.item()

    def _batch_state_dicts(
        self, state_dicts: list[dict[str, Tensor]]
    ) -> dict[str, Tensor]:
        """状態辞書のリストをバッチ化。"""
        keys = state_dicts[0].keys()
        batched: dict[str, Tensor] = {}
        for key in keys:
            batched[key] = torch.stack([sd[key] for sd in state_dicts]).to(self.device)
        return batched

    def save_checkpoint(
        self,
        path: str,
        episode: int,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """チェックポイントを保存。

        Args:
            path: 保存先パス。
            episode: 現在のエピソード番号。
            metrics: 保存するメトリクス (オプション)。
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "episode": episode,
                "metrics": metrics or {},
            },
            path,
        )

    def load_checkpoint(self, path: str) -> dict[str, Any]:
        """チェックポイントを読み込み。

        Args:
            path: チェックポイントのパス。

        Returns:
            チェックポイント辞書。
        """
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        return checkpoint
