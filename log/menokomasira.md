# メノコマシラデッキ 開発作業ログ (menokomasira.md)

本ファイルは、メノコマシラデッキエージェントの開発作業ログです。

## [2026-06-23] メノコマシラのニャースex/ドーミラー展開抑制

### 1. 作業概要
- `Meowth ex` は、手札にサポートがなく、サポート権が残っていて展開・進化・エネルギーなどに触る必要がある場合だけベンチ展開を評価するよう変更。
- セットアップ時の任意ベンチでは `Meowth ex` を基本的に出さないよう調整。
- `Bronzor` がバトル場にいて、すでに他の盤面がある場合は追加の `Bronzor` ベンチ展開をマイナス評価へ変更。
- バトル場の `Bronzor` が傷んでいる、または他に盤面/手札の種がない場合だけ、2体目 `Bronzor` をバックアップとして許容。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/menokomasira/main.py` | 🟠 重大 | ニャースexとドーミラーの展開・ベンチ選択評価を条件付きに変更。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- 合成ケースで、サポートが手札にある `Meowth ex` はプレイ/ベンチともマイナス、サポートなしで展開が必要な場合のみプラスになることを確認。
- 合成ケースで、アクティブ `Bronzor` かつ他の盤面がある場合は追加 `Bronzor` がマイナス、盤面バックアップが必要な場合のみプラスになることを確認。
- `python -m black agents_draft/menokomasira/main.py` が正常終了。
- `python -m py_compile agents_draft/menokomasira/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/menokomasira` が正常終了（135 steps, Result: 0）。

---

---

## [2026-06-23] メノコマシラのポケパッド取得評価を手札込みに修正

### 1. 作業概要
- `Poké Pad` の取得先評価を専用関数化し、盤面だけでなく手札の `Snorunt` / `Bronzor` / `Munkidori` / 進化札を確認するよう変更。
- 場にも手札にも進化元がない場合、`Froslass` / `Bronzong` より `Snorunt` / `Bronzor` / `Munkidori` を優先するよう調整。
- 手札に種がある場合は、その種を後から展開できる前提で進化札も候補に残すようにした。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/menokomasira/main.py` | 🟠 重大 | ポケパッド解決中のポケモン取得評価を手札込みで再設計。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- 合成ケースで、場・手札に種がない場合は `Snorunt` > `Munkidori` > `Bronzor` となり、進化元なしの `Froslass` / `Bronzong` は低評価になることを確認。
- `python -m black agents_draft/menokomasira/main.py` が正常終了。
- `python -m py_compile agents_draft/menokomasira/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/menokomasira` が正常終了（100 steps, Result: 1）。
- `scratch/menokomasira_pokepad_check.html` の確認で、ポケパッド1回目は `Bronzor`、2回目は手札・盤面が整った後に `Froslass` を取得。

---

---

## [2026-06-23] メノコマシラ新リスト対応

### 1. 作業概要
- 改良後の `agents_draft/menokomasira/deck.csv` に合わせ、`agents_draft/menokomasira/main.py` の盤面目標を更新。
- ユキワラシ系3ライン、通常ユキメノコ2体、マシマシラ2体以上を狙う評価へ変更。
- `Poké Pad` / `Ultra Ball` / `Hilda` / `Brock’s Scouting` / `Lana’s Aid` のサーチ・回収先を、通常ユキメノコとマシマシラ厚めの構築に合わせて調整。
- `Salvatore` は `Mega Froslass ex` だけに寄りすぎないよう、ドータクン進化も状況評価するよう修正。
- エネルギー評価は、マシマシラへの悪エネルギー、ドータクンへの超/テレパスエネルギー、ユキメノコ系への水エネルギーを新構築向けに再調整。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/menokomasira/main.py` | 🟠 重大 | 新デッキリストに合わせて展開・進化・回収・エネ評価を更新。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/menokomasira/main.py` が正常終了。
- `python -m py_compile agents_draft/menokomasira/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/menokomasira` が正常終了（122 steps, Result: 0）。
- 20戦ベンチ結果: `sample_abomasnow` 3勝17敗、`sample_dragapult` 2勝18敗、`sample_iono` 1勝19敗、`sample_lucario` 3勝17敗。全てクラッシュ0件。

---

---

## [2026-06-23] メノコマシラ初版エージェント作成

### 1. 作業概要
- `agents_draft/menokomasira/main.py` を、ユキメノコ/マシマシラ/ドータクン用の専用ロジックへ全面置換。
- `Snorunt` / `Bronzor` / `Munkidori` 展開、`Salvatore` による `Mega Froslass ex` / `Bronzong` 進化、`Froslass` のダメカン蓄積と `Munkidori` の `Adrena-Brain` 移動を軸に評価を実装。
- `Bronzong` の `Evolution Jammer`、`Mega Froslass ex` の手札参照打点、`Crispin` / `Hilda` / `Brock’s Scouting` / `Poké Pad` / `Ultra Ball` などのサーチ先評価を追加。
- MAIN選択では複数アクションを同時返却しないよう、最良1アクションのみ選ぶ処理に修正。

### 2. 変更されたファイル
| ファイル | 深刻度 | 変更内容 |
|---------|--------|---------|
| `agents_draft/menokomasira/main.py` | 🔴 根本変更 | メノコマシラ用エージェントとして全面書き換え。 |
| `LOG.md` | 🟡 軽微 | 本作業ログを追記。 |

### 3. 検証結果
- `python -m black agents_draft/menokomasira/main.py` が正常終了。
- `python -m py_compile agents_draft/menokomasira/main.py` が正常終了。
- `python tests/dry_run.py --agent-dir agents_draft/menokomasira` が正常終了（44 steps, Result: 0）。
- 20戦ベンチ結果（MAIN単手化後）: `sample_abomasnow` 0勝20敗、`sample_dragapult` 3勝17敗、`sample_iono` 0勝20敗、`sample_lucario` 5勝15敗。全てクラッシュ0件。

---
