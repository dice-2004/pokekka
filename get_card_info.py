"""
ポケモンカードのデッキリストカード情報取得スクリプト

LocketDonkarasuのデッキに含まれるすべてのカード詳細情報を取得します。
攻撃情報だけでなく、カードタイプ、HP、進化段階などの情報も表示します。
"""

import sys
from agents_draft.LocketDonkarasu.cg import api

# デッキリスト (Locket Donkarasu from main.py)
DECK_CARDS = {
    "Team_Rocket_s_Murkrow": 463,
    "Team_Rocket_s_Honchkrow": 891,
    "Team_Rocket_s_Porygon": 473,
    "Team_Rocket_s_Porygon2": 474,
    "Team_Rocket_s_Porygon_Z": 475,
    "Team_Rocket_s_Articuno": 414,
    "Roto_Stick": 1077,
    "Air_Balloon": 1174,
    "Brave_Bangle": 1175,
    "Miracle_Headset": 1109,
    "Team_Rocket_s_Transceiver": 1134,
    "Night_Stretcher": 1097,
    "Poke_Pad": 1152,
    "Team_Rocket_s_Ariana": 1216,
    "Team_Rocket_s_Archer": 1217,
    "Team_Rocket_s_Giovanni": 1218,
    "Team_Rocket_s_Petrel": 1219,
    "Team_Rocket_s_Proton": 1220,
    "Team_Rocket_s_Factory": 1257,
    "Team_Rocket_s_Energy": 15,
    "Ignition_Energy": 17,
}


def card_type_str(card_type):
    """カードタイプを文字列に変換"""
    types = {
        0: "POKEMON",
        1: "ITEM",
        2: "TOOL",
        3: "SUPPORTER",
        4: "STADIUM",
        5: "BASIC_ENERGY",
        6: "SPECIAL_ENERGY",
    }
    return types.get(card_type, "UNKNOWN")


def energy_str(energy_type):
    """エネルギータイプを文字列に変換"""
    energies = {
        0: "COLORLESS",
        1: "GRASS",
        2: "FIRE",
        3: "WATER",
        4: "LIGHTNING",
        5: "PSYCHIC",
        6: "FIGHTING",
        7: "DARKNESS",
        8: "METAL",
        9: "DRAGON",
        10: "RAINBOW",
        11: "TEAM_ROCKET",
    }
    return energies.get(energy_type, "UNKNOWN")


def print_all_deck_cards():
    """デッキのすべてのカード情報を表示"""
    print("\n" + "=" * 100)
    print("【ポケモンカードデッキリスト情報】")
    print("=" * 100)

    all_cards = api.all_card_data()
    all_attacks = {a.attackId: a for a in api.all_attack()}

    for card_name, card_id in sorted(DECK_CARDS.items(), key=lambda x: x[1]):
        card = next((c for c in all_cards if c.cardId == card_id), None)
        if card:
            print(f"\n【{card.name}】")
            print(f"  カードID: {card.cardId}")
            print(f"  カード名 (変数): {card_name}")
            print(f"  カードタイプ: {card_type_str(card.cardType)}")

            if card.cardType == api.CardType.POKEMON:
                stage = (
                    "ベース"
                    if card.basic
                    else (
                        f"Stage 1 (from {card.evolvesFrom})"
                        if card.stage1
                        else f"Stage 2 (from {card.evolvesFrom})"
                    )
                )
                print(f"  進化段階: {stage}")
                print(f"  HP: {card.hp}")
                print(f"  エネルギータイプ: {energy_str(card.energyType)}")
                print(f"  撤退コスト: {card.retreatCost}")

                if card.weakness:
                    print(f"  弱点: {energy_str(card.weakness)}")
                if card.resistance:
                    print(f"  抵抗: {energy_str(card.resistance)}")

                if card.ex:
                    ex_type = "Mega Evolution ex" if card.megaEx else "ex"
                    print(f"  特性: {ex_type}")
                if card.tera:
                    print(f"  特性: Tera (ベンチ時ダメージ無効)")

                if card.attacks:
                    print(f"  攻撃: {len(card.attacks)}個")
                    for attack_id in card.attacks:
                        attack = all_attacks.get(attack_id)
                        if attack:
                            energy_cost = [energy_str(e) for e in attack.energies]
                            print(f"    - {attack.name} (ID: {attack.attackId})")
                            print(
                                f"      必要: {energy_cost}, ダメージ: {attack.damage}"
                            )
                            if attack.text:
                                print(f"      効果: {attack.text}")

            if card.aceSpec:
                print(f"  特性: ACE SPEC (デッキに1枚まで)")

            if card.skills:
                print(f"  能力/スキル: {len(card.skills)}個")
                for skill in card.skills:
                    print(f"    - {skill.name}: {skill.text}")


def print_single_card(card_id):
    """指定されたカードIDの情報を表示"""
    all_cards = api.all_card_data()
    all_attacks = {a.attackId: a for a in api.all_attack()}

    card = next((c for c in all_cards if c.cardId == card_id), None)
    if card:
        print(f"\n【{card.name}】")
        print(f"  カードID: {card.cardId}")
        print(f"  カードタイプ: {card_type_str(card.cardType)}")
        print(f"  詳細情報:")
        if card.cardType == api.CardType.POKEMON:
            print(f"    HP: {card.hp}")
            print(f"    エネルギータイプ: {energy_str(card.energyType)}")
            print(f"    撤退コスト: {card.retreatCost}")
        print()
    else:
        print(f"カードID {card_id} は見つかりません。")


def print_card_search(search_term):
    """カード名で検索して情報を表示"""
    all_cards = api.all_card_data()
    search_lower = search_term.lower()
    matching = [c for c in all_cards if search_lower in c.name.lower()]

    if matching:
        print(f"\n【検索結果: {len(matching)}件】")
        for card in matching[:10]:  # 最初の10件を表示
            print(
                f"  ID: {card.cardId}, 名前: {card.name}, タイプ: {card_type_str(card.cardType)}"
            )
    else:
        print(f"'{search_term}' に一致するカードが見つかりません。")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--all" or arg == "-a":
            print_all_deck_cards()
        elif arg.isdigit():
            print_single_card(int(arg))
        else:
            print_card_search(arg)
    else:
        # 対話モード
        print("ポケモンカード情報取得ツール")
        print("1: デッキのすべてのカード情報を表示")
        print("2: カードIDで検索")
        print("3: カード名で検索")

        try:
            choice = input("\n選択 (1-3): ").strip()

            if choice == "1":
                print_all_deck_cards()
            elif choice == "2":
                card_id = int(input("カードID: "))
                print_single_card(card_id)
            elif choice == "3":
                search_term = input("カード名: ")
                print_card_search(search_term)
        except EOFError:
            # パイプからの入力の場合
            print_all_deck_cards()
