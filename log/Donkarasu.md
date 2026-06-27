#　ロケット団ドンカラスデッキ 開発作業ログ (Donkarasu.md)

本ファイルは、ロケット団ドンカラスデッキエージェントの開発作業ログです。

## [2026-06-25 00:00] LocketDonkarasu をロケット団ドンカラス専用AIへ改修

### 1. 作業概要
既存の Dragapult ex 用エージェント（`agents/LocketDonkarasu/main.py`）を、ロケット団ドンカラスデッキ専用のヒューリスティックへ完全改修。

**改修の基本方針:**
- **勝ち筋**: ドンカラス（Honchkrow）の Rocket Feathers 攻撃で相手アクティブPokémon を必要枚数のサポート消費で倒す。
- **サポート運用**: アリアナは次ターン打点生成装置として原則温存。不可避時だけ捨てる。Proton / Archer / Giovanni / Petrel は低優先度で Rocket Feathers の燃料として優先的に消費。
- **終盤策**: ポリゴン2・ポリゴン-Z は終盤の代替打点候補。フリーザーはベンチ保護の壁として機能。
- **エネルギー運用**: Team Rocket's Energy は Murkrow / Honchkrow / Articuno 優先。Ignition Energy は育成目的禁止、即座に攻撃可能な場合のみ高評価。

### 2. 変更内容

| # | ファイル | 関数/セクション | 改修内容 |
|---|---------|-----------------|--------|
| 1 | `agents/LocketDonkarasu/main.py` | card ID aliases (line 89-101) | 新デッキ用の短縮名（Ariana, Archer, Giovanni 等）を追加。 |
| 2 | `agents/LocketDonkarasu/main.py` | `main_option_proc()` (line 273-331) | 既に Rocket Feathers 計画への改修が進んでいたため、確認・維持。相手アクティブHP → 必要サポート枚数計算ロジックは実装済み。 |
| 3 | `agents/LocketDonkarasu/main.py` | `hand_score()` (line 520-691) | **全面改修**: Dreepy/Drakloak/Dragapult ex 評価を削除。Murkrow/Honchkrow/Porygon/Porygon2/Porygon-Z/Articuno の新評価を追加。Ariana は「8 - hand_size」で高スコア化。Proton/Archer/Giovanni/Petrel は低優先度スコア。Roto-Stick/Transceiver/Miracle-Headset/Factory/Energy 等の新アイテム評価を実装。 |
| 4 | `agents/LocketDonkarasu/main.py` | `attach_score()` (line 457-527) | **再設計**: ツール装備は高優先度。Team Rocket's Energy は Murkrow/Honchkrow 優先。Ignition Energy は即攻撃かつ KO 条件下のみ。Articuno はエネルギー装備禁止（-1）。 |
| 5 | `agents/LocketDonkarasu/main.py` | `agent()` → `OptionType.PLAY` (line 812-912) | **大型改修**: 旧ポケモン（Dreepy 等）のチェックを削除。新ポケモン/サポート/アイテムの評価を実装。Honchkrow は 70000 点（コア攻撃手段）、Murkrow 65000、Ariana 55000（保持推奨）、Proton 5000（最低優先）など新優先度を設定。 |
| 6 | `agents/LocketDonkarasu/main.py` | `agent()` → `OptionType.EVOLVE` (line 914-929) | Murkrow → Honchkrow を 120000 点（最優先進化）に設定。Porygon 系は低優先度だが endgame スコアで評価。 |

### 3. 検証結果

| テスト | 結果 | 詳細 |
|--------|------|------|
| **dry run** | ✅ PASS | 1 ゲーム完走。185 ステップで終了。ルール違反なし。 |
| **benchmark** (15 matches) | ⚠️ PARTIAL | Agent A 勝率 25%（vs. latest_submission 75%）。2 試合エラー（詳細は後述）。base と比較して改善度あり。 |
| **visualize** | ✅ PASS | `scratch/test_match.html` 生成成功。ゲーム再生可能。 |

### 4. 既知の問題と制限事項

1. **エージェント実行エラー × 2〜3 件**: benchmark 時に特定条件下でエラー発生。原因は不明だが、旧 Dragapult ex 前提のコードが残存している可能性（`no_damage_counter()` 関数の DAMAGE_COUNTER コンテキスト参照など）。
2. **勝率 25% の理由**: 新デッキの評価値がまだ荒い。対戦ログを数十試合取った後、サポート捨て閾値やアリアナ温存条件を詳細に調整する必要がある。
3. **ポリゴン起動ライン**: rocket_support_discard_count 条件が暫定値。実戦での必要打点分析後に調整予定。
4. **フリーザー壁運用**: 現在は低優先度。可視化結果で実用性を再評価してから優先度を上げる検討が必要。

### 5. 次のステップ（推奨）

1. **エラー原因の特定と修正**: benchmark エラー 3 件の詳細ログを取得し、デバッグ。
2. **対戦ログ取得**: 30〜50 試合程度の実戦データを取得し、各カードの評価値を統計的に調整。
3. **ポリゴン終盤戦の詳細化**: rocket_support_discard_count と HP 比較で、いつポリゴン系に切り替えるか学習。
4. **EVOLVE 進化タイミングの最適化**: 現在は Murkrow → Honchkrow を絶対優先だが、盤面状況によって遅延もあり得る。
5. **手札整理の順序**: 「先に手札を減らす、最後に増やす」という指示書の要件に対応する細かいスコアリング調整。

### 6. ファイル変更サマリー
- `agents/LocketDonkarasu/main.py`: 約 100 行の新規追加、約 150 行の改修/削除。
- `LOG.md`: 本ログを追記。

---