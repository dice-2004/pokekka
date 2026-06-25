"""
ポケモンカードデッキリストのカード情報取得スクリプト

LocketDonkarasu (またはその他のエージェント)のデッキに含まれるすべてのカード
の詳細情報を取得します。攻撃情報だけでなく、カードタイプ、HP、進化段階などの
すべての情報を表示します。
"""

import sys
from agents.LocketDonkarasu.cg import api


def find_card(all_cards, card_id):
    """
    カードIDでカードを検索します。

    Args:
        all_cards: すべてのCardDataオブジェクトのリスト
        card_id: 検索するカードID (int)

    Returns:
        見つかったCardDataオブジェクト、または見つからなかった場合はNone
    """
    for card in all_cards:
        if card.cardId == card_id:
            return card
    return None


def get_deck_list():
    """
    LocketDonkarasuのデッキリストを返します。
    {カード名: カードID, ...}の辞書形式
    """
    deck_list = {
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
    return deck_list


def card_type_to_string(card_type):
    """CardTypeをわかりやすい文字列に変換します。"""
    type_map = {
        0: "POKEMON",
        1: "ITEM",
        2: "TOOL",
        3: "SUPPORTER",
        4: "STADIUM",
        5: "BASIC_ENERGY",
        6: "SPECIAL_ENERGY",
    }
    return type_map.get(card_type, "UNKNOWN")


def energy_type_to_string(energy_type):
    """EnergyTypeをわかりやすい文字列に変換します。"""
    type_map = {
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
    return type_map.get(energy_type, "UNKNOWN")


def print_card_details(card):
    """
    カードの詳細情報をきれいく印字します。

    Args:
        card: CardDataオブジェクト
    """
    print("=" * 80)
    print(f"カード名: {card.name}")
    print(f"カードID: {card.cardId}")
    print(f"カードタイプ: {card_type_to_string(card.cardType)}")

    if card.cardType == api.CardType.POKEMON:
        print(f"HP: {card.hp}")
        if card.basic:
            print("進化段階: ベース")
        elif card.stage1:
            print(f"進化段階: Stage 1 (進化元: {card.evolvesFrom})")
        elif card.stage2:
            print(f"進化段階: Stage 2 (進化元: {card.evolvesFrom})")

        if card.ex:
            print("特性: ex", end="")
            if card.megaEx:
                print(" (Mega Evolution)")
            else:
                print()

        if card.tera:
            print("特性: Tera")

        print(f"エネルギータイプ: {energy_type_to_string(card.energyType)}")
        print(f"撤退コスト: {card.retreatCost}")

        if card.weakness:
            print(f"弱点: {energy_type_to_string(card.weakness)}")
        if card.resistance:
            print(f"抵抗: {energy_type_to_string(card.resistance)}")

        if card.attacks:
            print(f"\n攻撃数: {len(card.attacks)}")
            print("攻撃IDs:", card.attacks)

    if card.aceSpec:
        print("特性: ACE SPEC")

    if card.skills:
        print(f"\nスキル数: {len(card.skills)}")
        for skill in card.skills:
            print(f"  - {skill.name}: {skill.text}")

    print("=" * 80)
    print()


def display_attack_details(card, all_attack_ids):
    """
    カードの攻撃詳細情報を表示します。

    Args:
        card: CardDataオブジェクト
        all_attack_ids: {attackId: Attackオブジェクト}の辞書
    """
    if not card.attacks:
        return

    print(f"\n【{card.name}の攻撃詳細】")
    print("-" * 80)
    for attack_id in card.attacks:
        attack = all_attack_ids.get(attack_id)
        if attack:
            print(f"攻撃ID: {attack.attackId}")
            print(f"攻撃名: {attack.name}")
            print(f"ダメージ: {attack.damage}")
            print(
                f"必要エネルギー: {[energy_type_to_string(e) for e in attack.energies]}"
            )
            print(f"効果テキスト: {attack.text}")
            print("-" * 80)


def main():
    """メイン処理"""
    print("ポケモンカードデッキ情報取得ツール\n")

    # APIからすべてのカードと攻撃データを取得
    all_attack_ids = {a.attackId: a for a in api.all_attack()}
    all_cards = api.all_card_data()

    # デッキリストを取得
    deck_list = get_deck_list()

    print(f"デッキに含まれるカード数: {len(deck_list)}\n")

    # ユーザーに選択肢を提示
    print("【表示オプション】")
    print("1: すべてのカード情報を表示")
    print("2: 特定のカードID情報を表示")
    print("3: カード名で検索")

    choice = input("\n選択 (1-3): ").strip()

    if choice == "1":
        # すべてのカード情報を表示
        print("\n【デッキリストのすべてのカード情報】\n")
        for card_name, card_id in sorted(deck_list.items(), key=lambda x: x[1]):
            card = find_card(all_cards, card_id)
            if card:
                print_card_details(card)
                display_attack_details(card, all_attack_ids)
            else:
                print(f"警告: カードID {card_id} ({card_name}) が見つかりません。")

    elif choice == "2":
        # 特定のカードID情報を表示
        try:
            card_id = int(input("\nカードIDを入力: "))
            card = find_card(all_cards, card_id)
            if card:
                print_card_details(card)
                display_attack_details(card, all_attack_ids)
            else:
                print(f"カードID {card_id} が見つかりません。")
        except ValueError:
            print("無効な入力です。数値を入力してください。")

    elif choice == "3":
        # カード名で検索
        search_name = input("\nカード名を入力 (部分一致): ").strip().lower()
        matching_cards = [
            card for card in all_cards if search_name in card.name.lower()
        ]

        if matching_cards:
            print(f"\n【検索結果: {len(matching_cards)}件】\n")
            for card in matching_cards:
                print_card_details(card)
                display_attack_details(card, all_attack_ids)
        else:
            print(f"'{search_name}' に一致するカードが見つかりません。")

    else:
        print("無効な選択です。")


if __name__ == "__main__":
    main()
