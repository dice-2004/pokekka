# キュワワーレガシーデッキ 開発作業ログ (kyuwawa_tan_regasy.md)

本ファイルは、キュワワーレガシーデッキエージェントの開発作業ログです。

## [2026-06-23] 暗号マニア選択の逐次評価化

### 1. 作業概要
- `Ciphermaniac’s Codebreaking`（暗号マニアの解読）の2枚選択を、独立スコア上位2枚ではなく逐次評価に変更。
- 1枚目を現盤面で選び、そのカードを仮の将来手札として加えた状態で2枚目を再評価する専用 chooser を追加。
- 妨害札を優先する「余裕あり」条件を、次の番に化石をベンチへ置きつつキュワワーで攻撃できる場合に限定。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | 暗号マニアの山札積み選択を逐次評価化し、妨害札優先条件を厳格化。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（45 steps, Result: 1）。
- 合成盤面で、化石不足時は `Antique Cover Fossil` → `Xerosics Machinations`、化石あり・エネなし時は `Energy Search` → `Xerosics Machinations` となり、1枚目を含めて2枚目を再評価していることを確認。

---

---

## [2026-06-23] MAIN選択のプランナー化

### 1. 作業概要
- `SelectContext.MAIN` で手札カードを点数順に使う方式を停止し、明示的な行動プランナーを追加。
- 盤面維持、キュワワー復帰、エネルギー確保、化石/スタジアム整備、妨害、攻撃の順に「使う/使わない」と順番を判定する構造へ変更。
- 非MAINの対象選択（サーチ先、ディスカード先、ダメージ先など）は既存の評価関数を維持。
- `agent()` はMAIN時にプランナーの結果を優先し、従来の `score_play_card` / `order_scores_for_execution` による手札順ソートを通らないよう変更。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🔴 根本変更 | MAIN行動選択をスコアソートから明示プランナーへ変更。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（66 steps, Result: 1）。
- 合成盤面で、ベンチ化石0枚なら化石、化石あり・エネなしなら `Energy Search`、化石不足かつ手札7枚なら `Hand Trimmer` より化石を先に選ぶことを確認。
- 10戦ベンチ結果: `sample_abomasnow` 5勝5敗、`sample_dragapult` 3勝7敗、`sample_iono` 2勝8敗、`sample_lucario` 8勝2敗。全てクラッシュ0件。

---

---

## [2026-06-23] ハンドトリマー使用順の調整

### 1. 作業概要
- `Hand Trimmer` 使用時に自分も手札を捨てる局面を検出する補助関数を追加。
- 化石・スタジアム・一部サポート・エネルギー手貼りなど、実質的に手札を減らす有用アクションがある場合は、それらを `Hand Trimmer` より先に実行するよう順序補正を追加。
- 自分が追加で捨てない手札枚数では、従来通り `Hand Trimmer` の高評価を維持。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | ハンドトリマー使用前の手札削減アクション優先補正を追加。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（55 steps, Result: 0）。
- 合成盤面で、手札7枚時は `Hand Trimmer` が化石より下に補正され、手札6枚時は補正されないことを確認。

---

---

## [2026-06-22] ラムダ取得評価の状況別調整

### 1. 作業概要
- `Team Rocket's Petrel`（ラムダ）の取得評価を、ベンチ化石0枚の緊急時とそれ以外で分岐。
- ベンチに化石がある局面では、エネルギー不足なら `Energy Search` やエネルギー回収、トラッシュに基本エネがあるなら `Night Stretcher` を優先。
- 復帰札がない局面では `Night Stretcher` / `Lana’s Aid` を化石より上に評価し、不要な追加化石取得を抑制。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | ラムダ解決中の取得カード評価を状況別に調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（38 steps, Result: 0）。
- ラムダ取得評価の簡易チェックで、ベンチ化石0枚では化石、ベンチ化石あり・エネなしでは `Energy Search`、基本エネがトラッシュにある場合は `Night Stretcher` が化石より上になることを確認。

---

---

## [2026-06-22] ラムダ取得時の化石優先化

### 1. 作業概要
- `Team Rocket's Petrel`（ラムダ）解決中の `TO_HAND` 評価を専用化。
- 化石アクセスが必要な局面では、暗号マニアより化石を明確に優先するよう調整。
- ラムダ中に化石が見えていない場合でも、暗号マニアや次のラムダは低めの代替評価に抑制。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | ラムダ解決中の取得カード評価を追加。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（49 steps, Result: 1）。
- `scratch/visualizer.html` のラムダ選択ステップを新評価で採点し、化石が 59500〜60400 点で上位、暗号マニアは上位外になることを確認。

---

---

## [2026-06-22] 化石温存とベンチ展開評価の調整

### 1. 作業概要
- キュワワーで即攻撃できない局面では、アクティブ化石をトラッシュして入れ替える評価を抑制。
- 化石をベンチに出す評価を全体的に引き上げ、特にベンチ化石0枚・化石不足時の優先度を強化。
- 余剰化石の自己トラッシュ/ディスカード評価を負点寄りにし、意味の薄い化石トラッシュを避けるよう調整。
- ベンチ化石がない場面の実行順補正を `30000` から `36000` へ引き上げ。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | 化石トラッシュ抑制、化石ベンチ展開評価、実行順補正を調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（51 steps, Result: 0）。
- 20戦ベンチ結果: `sample_abomasnow` 1勝19敗、`sample_dragapult` 2勝18敗、`sample_iono` 10勝10敗、`sample_lucario` 11勝9敗。全てクラッシュ0件。

---

---

## [2026-06-22] レガシー版の盤面切れ負け対策

### 1. 作業概要
- `Flower Shower` 後に返しの攻撃で盤面0になる局面を避けるため、ベンチなしのキュワワー攻撃評価を抑制。
- アクティブ化石をどかしてキュワワーで攻撃する評価に、ベンチ化石の有無と返しのKOリスクを反映。
- Dragapult系のダメカン圧に対して `Antique Cover Fossil` を優先し、`Budew` のItemロックは `Play Rough` で処理しやすく調整。
- `Iono's Voltorb` と `Kyogre` の可変火力を危険度推定に追加。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | 盤面維持、Cover Fossil優先、Budew対策、可変火力推定を調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（40 steps, Result: 1）。
- 100戦ベンチ結果: `sample_abomasnow` 12勝88敗、`sample_dragapult` 8勝92敗、`sample_iono` 44勝56敗、`sample_lucario` 61勝39敗、合計125勝275敗。
- 修正前の合計82勝318敗から、合計勝率は20.5%→31.25%に改善。

---

---

## [2026-06-22] レガシー版の妨害札と暗号マニア積み先改善

### 1. 作業概要
- 次ターンのキュワワー復帰が見えていて、現在の攻撃ルートがサポート権を使わずに成立する場合、`Xerosics Machinations` を積極的に使うよう評価を引き上げ。
- `Xerosics Machinations` を優先できない場面でも、相手手札が7枚以上なら `Hand Trimmer` を攻撃前に使いやすい点数へ調整。
- `Ciphermaniacs Codebreaking` の山札上配置を、復帰が見えている場合は妨害札、見えていない場合はキュワワー復帰札・エネルギー札を優先する専用評価に変更。
- 復帰判定を、トラッシュだけでなく手札の回収札・エネルギー札・現在場のキュワワーまで含めて「次ターンに復帰できるか」を見る形に修正。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | クセロシキ、ハンドトリマー、暗号マニア選択、復帰判定、攻撃前実行順を調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（69 steps, Result: 1）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- `python tests/benchmark.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --matches 4 --workers 1` はクラッシュ0件、0勝4敗。
- 合成盤面で、復帰可の `Xerosics Machinations` が 47950、`Flower Shower` が 36000、サポート使用済みの `Hand Trimmer` が 40500、暗号マニアの復帰可時はクセロシキ優先、復帰不可時は `Night Stretcher` 優先になることを確認。

---

---

## [2026-06-22] レガシー版の化石アクセス改善

### 1. 作業概要
- `Antique Root Fossil` を `FOSSILS` に追加し、デッキ内4枚が化石展開・後続判定・保持評価に乗るように修正。
- `Ciphermaniac’s Codebreaking` をサポーター評価に追加し、化石不足時に山札上へ化石や復帰札を積んで `Flower Shower` で引き込む動きを評価するようにした。
- `Ciphermaniac’s Codebreaking` の解決中は、山札へ戻す/積むカード選択でも通常の保持価値ではなく取得価値を使うように調整。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | Root Fossil の化石扱い化、Ciphermaniac のプレイ/選択評価を追加。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m black --check agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（30 steps, Result: 0）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- 16戦デバッグ集計で化石プレイ15回、そのうち `Antique Root Fossil` 8回を確認。
- `python tests/benchmark.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --matches 4 --workers 1` はクラッシュ0件。

---

---

## [2026-06-22] レガシー版のキュワワー復帰攻撃ライン強化

### 1. 作業概要
- 手札のキュワワーを出せば同ターンに `Flower Shower` へ届く場面で、キュワワーのプレイ評価を大幅に引き上げ。
- `Night Stretcher` / `Lana's Aid` / `Team Rocket's Petrel` / `Pokégear 3.0` からキュワワーを回収して攻撃に届くラインを高評価に変更。
- バトル場が化石でベンチのキュワワーを前に出せば攻撃できる場合、化石をどかす処理の評価を大幅に引き上げ。
- 復帰ライン判定で、エネルギー添付済みフラグを `State.energyAttached` から参照するよう修正。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | キュワワー手札出し・回収・化石前解除からの攻撃ラインを高評価化。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（36 steps, Result: 1）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- 合成盤面で、手札キュワワーのプレイ 44000、`Night Stretcher` 43000、化石前解除 45000 の評価になることを確認。
- `python tests/benchmark.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --matches 4 --workers 1` はクラッシュ0件、1勝3敗。

---

---

## [2026-06-22] レガシー版のキュワワー攻撃優先度強化

### 1. 作業概要
- `Flower Shower` の基礎スコアを引き上げ、妨害・スタジアム・追加サーチより攻撃を選びやすくした。
- `Flower Shower` がすでに選択可能な場面では、スタジアム、サーチ、2体目以降の化石展開で攻撃を後回しにしないよう実行順制御を変更。
- 攻撃前に残す最低限のセットアップは、エネルギー装着とベンチ化石0体時の後続確保に絞った。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | `Flower Shower` スコアと攻撃前セットアップ判定を調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（28 steps, Result: 1）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- vs `sample_deck/sample_abomasnow` 12戦デバッグ集計で、`Flower Shower` 選択可能25回中18回選択、`END` 優先0回を確認。
- `python tests/benchmark.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --matches 4 --workers 1` はクラッシュ0件、1勝3敗。

---

---

## [2026-06-22] キュワワーLOレガシー版の方針変更

### 1. 作業概要
- `agents_draft/kyuwawa-tan-regasy/main.py` を新デッキ構成に合わせて更新。
- `Legacy Energy` を最優先級でキュワワーに装着し、基本超エネルギーより優先して技起動とサイド軽減を狙うようにした。
- 妨害札より `Flower Shower` を優先し、攻撃可能な場面では `END` せず、同ターン内で化石・エネルギー・スタジアム・サーチを処理してから攻撃する実行順へ調整。
- ベンチ化石を2〜3体目標にし、後続を絶やさないよう化石展開・取得・保持を強化。
- `Lively Stadium` / `Nighttime Mine` を積極的に貼る方針に変更し、コルレスや `Team Rocket's Petrel` などのサーチ候補でもスタジアムを高評価にした。
- 新規採用の `Energy Retrieval`、`Team Rocket's Petrel`、`Lillie's Determination`、`Nighttime Mine` を評価対象に追加。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/kyuwawa-tan-regasy/main.py` | 🟠 重大 | レガシー版デッキ向けに定数、装着、攻撃、化石、スタジアム、サポート評価を調整。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python -m py_compile agents_draft/kyuwawa-tan-regasy/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/kyuwawa-tan-regasy` が正常終了（65 steps, Result: 1）。
- `python tests/visualize_match.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --output scratch/visualizer.html` が正常終了。
- vs `sample_deck/sample_abomasnow` 16戦デバッグ集計で、レガシー装着9回、化石プレイ51回、初回化石展開17回、スタジアム40回、`Flower Shower`23回を確認。
- `Flower Shower` が選択肢にある場面で `END` を選んだケースは0回。
- `python tests/benchmark.py --agent-a agents_draft/kyuwawa-tan-regasy/main.py --agent-b sample_deck/sample_abomasnow/main.py --matches 4 --workers 1` はクラッシュ0件、1勝3敗。

---
