# キュワワー単LOデッキ 開発作業ログ (kyuwawa_tan.md)

本ファイルは、キュワワー単LOデッキエージェントの開発作業ログです。

## [2026-06-22] キュワワータンLO純粋戦略へのシフト

### 1. 作業概要
デッキ改良に伴い、戦略を **逃げ縛り型から純粋LO型** へシフト。以下の変更を実施：

| 削除 | 追加 | 理由 |
|-----|-----|------|
| ポスの指令（BOSS_ORDERS）× 4 | ポケモンキャッチャー（POKEMON_CATCHER）× 4 | 相手の逃げ縛りから脱却、相手の場制御に特化 |
| クラッシュハンマー（CRUSHING_HAMMER）× 4 | 化石（FOSSILS）× 調整 | エネルギー破壊戦術廃止、キュワワー展開安定化 |
| リーリエの決心（LILLIES_DETERMINATION）× 4 | ツウのバトル（THUG_BATTLE）× 4 | デッキサーチ減少、毎ターンキュワワー技撃を優先 |

### 2. main.py のスコアリング改良
- **Flower Shower スコア拡大**: 基礎スコア 32000→36000、ボーナス係数 750→1200
- **POKEMON_CATCHER 導入**: `score_play_card()` と `score_to_hand()` に新規追加（スコア 4200-8500）
- **XEROSICS_MACHINATIONS 強化**: 相手の場制御価値を 6200→7800 に引き上げ
- **trap_score 依存削除**: `score_option()` の END オプション判定から trap_score 参照を廃止
- **不要カード処理削除**: own_card_keep_value() / score_play_card() から BOSS_ORDERS、CRUSHING_HAMMER、LILLIES_DETERMINATION の評価を完全削除

### 3. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🔴 重大 | スコアリングロジック全面改良、カード定数更新 |
| `agents_draft/kyuwawa-tan-regasy/deck.csv` | 🔴 重大 | デッキリスト更新（ボスの指令・クラッシュハンマー・リーリエ削除、キャッチャー・化石・ツウのバトル追加） |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記 |

### 4. 検証結果
- ✅ `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了
- ✅ `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_lucario/main.py --output scratch/test_match.html` が正常終了
- ✅ ランタイムエラーなし、1試合実行完了

### 5. 期待される動作改善
- **毎ターンFlower Shower実行の優先度向上**: キュワワーエネルギー付与・化石展開が完了次第、サポート選択を抑制してAttackを選択しやすくなる
- **相手の場制御強化**: POKEMONキャッチャーで相手のダメージラインの高いポケモンを交換させやすくなり、デッキアウトまでの期間延長
- **エネルギー破壊廃止による簡潔性**: CRUSHING_HAMMER削除により、エネルギー付与に専念できる

### 6. 次のステップ
- 複数試合でのベンチマーク実施
- 相手の圧力別（ルールボックス、テラ、エフェクト）でのスコア調整
- trap_score 完全削除の検討（現在は GRAVITY_GEMSTONE のみ残存）

---

---

## [2026-06-22] 後続維持と化石前入れ替え抑制

### 1. 作業概要
- ベンチに化石の後続が0体のときは、場の化石総数が目標に達していても化石展開・取得・保持を優先するように調整。
- キュワワーを下げて化石を前に出す `SWITCH` は、相手アクティブが攻撃不能かつベンチ狙撃も見えない強いロック状況以外では低評価に変更。
- バトル場が化石でベンチがキュワワー単騎のとき、後続化石を再展開できない場合は化石トラッシュ/逃げの評価を下げ、相手サイド残数・次ターン火力・LO目前かどうかで補正するようにした。
- ニュートラルゾーンの緊急判定を相手アクティブ由来のex攻撃に限定し、ソルロックのような非exアクティブでキュワワーが倒される場面ではベンチex圧だけで貼らないようにした。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan/main.py` | 🟠 重大 | ベンチ後続評価、化石前入れ替え抑制、化石トラッシュ評価、ニュートラルゾーン緊急判定を調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan` が正常終了（70 steps, Result: 1）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- vs `sample_deck/sample_abomasnow` 12戦デバッグ集計で、化石プレイ18回、初回ベンチ化石展開12回、キュワワーから化石前への `SWITCH` 0回を確認。
- ソルロック前＋ベンチメガルカリオex圧の単体確認で、ニュートラルゾーン緊急判定が False になることを確認。

---

---

## [2026-06-22] ニュートラルゾーンの早貼り抑制

### 1. 作業概要
- ニュートラルゾーンを、単に相手のRule Box圧があるだけでは貼らないように調整。
- 相手の現在ポケモンおよび進化先exが次ターンに使える技火力を見て、こちらのアクティブが気絶し、そのまま敗北し得る場合のみ高優先度で貼るようにした。
- 相手が既にスタジアムを使っている場合はやや許容し、空のスタジアム枠への早貼りは基本的にマイナス評価へ変更。
- ニュートラルゾーンは手札では保持しやすくしつつ、プレイ判断は緊急時まで温存する方針にした。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan/main.py` | 🟠 重大 | ニュートラルゾーン緊急度評価とプレイスコアを調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan` が正常終了（49 steps, Result: 0）。
- vs `sample_deck/sample_lucario` 12戦サンプルで、ニュートラルゾーンのプレイ選択肢2回中、実際のプレイは1回。貼ったケースはリオルからメガルカリオexへの直近攻撃圧を見た場面。

---

---

## [2026-06-22] キュワワーLOエージェントの攻撃実行順制御追加

### 1. 作業概要
- 攻撃スコアは従来どおり「攻撃したい局面」の判断として残し、選択直前の実行順だけを調整する後処理を追加。
- MAINフェーズで目標枚数未達の化石や有効な道具装着が残っている場合、即LO勝ちになる `Flower Shower` を除き、攻撃/ENDを後回しにするようにした。
- 化石・道具・エネルギー装着・妨害など、同ターン内に両立できる行動を先に処理し、その後の再選択で攻撃する流れを狙う。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan/main.py` | 🟠 重大 | `order_scores_for_execution` による実行順制御を追加。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan` が正常終了（46 steps, Result: 0）。
- 古いリプレイ盤面の再評価で、元スコアでは `Flower Shower` が上でも、実行スコアでは `PLAY Antique Cover Fossil` が先になることを確認。
- vs `sample_deck/sample_abomasnow` 20戦デバッグ集計で、化石39回、`Flower Shower`26回、重力玉17回、ハンディファン8回の選択を確認。

---

---

## [2026-06-22] キュワワーLOエージェントの化石・道具活用強化

### 1. 作業概要
- 相手の場のポケモンからカードDB上の進化先を参照し、次ターンに1エネ追加で使える進化後の技火力まで評価するように変更。
- 進化込みの次回攻撃でキュワワーが気絶し得る場合、化石の目標展開枚数を増やすようにした。
- ベンチ狙撃が見えない対面では化石を出し渋らず、基本的に複数枚展開する方針へ変更。
- 重力玉を最優先道具として維持しつつ、重力玉が手札にない場合はハンディファンも活用するようにスコアを調整。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan/main.py` | 🟠 重大 | 進化先火力評価、化石目標枚数、道具活用スコアを調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan` が正常終了（42 steps, Result: 0）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- vs `sample_deck/sample_abomasnow` 4戦ベンチマークはクラッシュ0件、1勝3敗。
- vs `sample_deck/sample_abomasnow` 12戦デバッグ集計で、重力玉9回、化石18回、ハンディファン6回、`Flower Shower`15回の選択を確認。

---

---

## [2026-06-22] キュワワーLOエージェントのエネルギー装着バグ修正

### 1. 作業概要
- `OptionType.ATTACH` の `playerIndex` が `None` で渡されるケースを考慮できておらず、エネルギー/道具装着候補のカード取得に失敗していた問題を修正。
- `playerIndex` が `None` の場合は現在の自分プレイヤーの手札として扱うようにし、基本超エネルギーと重力玉の装着スコアが正しく効くようにした。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan/main.py` | 🔴 致命的 | `ATTACH` 選択肢のカード所有者解決を修正。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan` が正常終了（48 steps, Result: 0）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- デバッグトレースで `ATTACH Basic {P} Energy`、`ATTACK attackId=215`、`ATTACH Gravity Gemstone`、再度 `ATTACK attackId=215` を確認。

---

---

## [2026-06-22] キュワワーLOエージェントの重力玉・技優先度調整

### 1. 作業概要
- 重力玉を引いた場合は、キュワワーの道具枠へ最優先級で貼るようにスコアを大幅に引き上げ。
- ハンディファンで道具枠を埋めて重力玉を貼れなくなる動きを抑制。
- `Flower Shower` は自分の山札が尽きる危険がある場合を除き、常に前向きに使う方針へ変更。
- 技使用の前提になる基本超エネルギー到達を強めるため、エネルギーサーチ、コルレスの執念、ポケギアからのコルレス選択を優先。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan/main.py` | 🟠 重大 | 重力玉、基本超エネルギー確保、`Flower Shower` のスコアを調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan` が正常終了（159 steps, Result: 1）。
- `python tests/benchmark.py --agent-a agents_draft/kyuwawa-tan/main.py --agent-b sample_deck/sample_iono/main.py --matches 4 --workers 1` はクラッシュ 0 件、0勝4敗。

---

---

## [2026-06-22] キュワワーLOエージェント main.py 実装

### 1. 作業概要
- `agents_draft/kyuwawa-tan/main.py` をキュワワー単騎LOデッキ向けに実装。
- キュワワーの `Flower Shower` による山札切れ狙いを軸にしつつ、重力玉・ボスの指令・クラッシュハンマーで逃げ縛りを狙うスコアリングを追加。
- 化石は盤面と相手の攻撃圧に応じて必要最低限だけ出し、キュワワー気絶時の即敗北を避ける保険として扱う方針にした。
- 妨害札（エリ、クセロシキのたくらみ、ハンドトリマー、ポケモンキャッチャー等）と、山札枚数に応じた攻撃/ドロー抑制を実装。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan/main.py` | 🟠 重大 | サンプル実装をキュワワーLO用の決定論的ヒューリスティックに差し替え。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black --check agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan` が正常終了（最終確認: 149 steps, Result: 1）。
- 短期ベンチマークでクラッシュ 0 件を確認：
  - vs `sample_deck/sample_lucario`: 8戦 3勝5敗。
  - vs `sample_deck/sample_iono`: 8戦 3勝5敗。
  - vs `sample_deck/sample_dragapult`: 8戦 1勝7敗。

---
