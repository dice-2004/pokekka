import os
from collections import Counter, defaultdict

from cg.api import (
    AreaType,
    Card,
    CardType,
    EnergyType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_attack,
    all_card_data,
    to_observation_class,
)

"""
Cynthia's Garchomp ex Deck

ガバイトの「おうじゃのよびごえ」を継続的に使って盤面を作り、
複数のシロナのロズレイドでガブリアスexの1エネルギー技を強化する。
リューノバスターは、スクリューダイブでは倒せない相手を倒せる場面を
中心に使い、エネルギーを失った次の番も攻撃を続けられるようにする。
"""


def _load_deck() -> list[int]:
    file_path = "deck.csv"
    if not os.path.exists(file_path):
        file_path = "/kaggle_simulations/agent/" + file_path
    with open(file_path, "r", encoding="utf-8") as file:
        deck = [int(line) for line in file.read().splitlines() if line.strip()]
    return deck[:60]


my_deck = _load_deck()
card_table = {card.cardId: card for card in all_card_data()}
attack_table = {attack.attackId: attack for attack in all_attack()}
deck_total = Counter(my_deck)

# Pokémon
CYNTHIAS_ROSELIA = 341
CYNTHIAS_ROSERADE = 342
CYNTHIAS_GIBLE = 379
CYNTHIAS_GABITE = 380
CYNTHIAS_GARCHOMP_EX = 381

# Energy
BASIC_FIGHTING_ENERGY = 6
ROCK_FIGHTING_ENERGY = 20

# Trainer cards
RARE_CANDY = 1079
UNFAIR_STAMP = 1080
BUDDY_BUDDY_POFFIN = 1086
NIGHT_STRETCHER = 1097
POKEGEAR_3_0 = 1122
PREMIUM_POWER_PRO = 1141
FIGHTING_GONG = 1142
POKE_PAD = 1152
CYNTHIAS_POWER_WEIGHT = 1173
BOSSS_ORDERS = 1182
HILDA = 1225
JUDGE = 1213
TEAM_ROCKETS_PETREL = 1219
LILLIES_DETERMINATION = 1227
FOREST_OF_VITALITY = 1261

SUPPORTER_IDS = {
    BOSSS_ORDERS,
    HILDA,
    JUDGE,
    TEAM_ROCKETS_PETREL,
    LILLIES_DETERMINATION,
}
CYNTHIAS_POKEMON = {
    CYNTHIAS_ROSELIA,
    CYNTHIAS_ROSERADE,
    CYNTHIAS_GIBLE,
    CYNTHIAS_GABITE,
    CYNTHIAS_GARCHOMP_EX,
}
ENERGY_IDS = {BASIC_FIGHTING_ENERGY, ROCK_FIGHTING_ENERGY}

SCREW_DIVE = 531
DRACONIC_BUSTER = 532

premium_turn = -1
premium_used = False


def get_card(
    obs: Observation,
    area: AreaType | None,
    index: int | None,
    player_index: int | None,
) -> Pokemon | Card | None:
    """指定された場所からカードを安全に取得する。"""
    if area is None or index is None or player_index is None:
        return None
    state = obs.current
    if state is None:
        return None
    player = state.players[player_index]
    try:
        if area == AreaType.DECK:
            return obs.select.deck[index] if obs.select.deck is not None else None
        if area == AreaType.HAND:
            return player.hand[index] if player.hand is not None else None
        if area == AreaType.DISCARD:
            return player.discard[index]
        if area == AreaType.ACTIVE:
            return player.active[index]
        if area == AreaType.BENCH:
            return player.bench[index]
        if area == AreaType.PRIZE:
            return player.prize[index]
        if area == AreaType.STADIUM:
            return state.stadium[index]
        if area == AreaType.LOOKING:
            return state.looking[index] if state.looking is not None else None
    except (IndexError, TypeError):
        return None
    return None


def _all_in_play(player) -> list[Pokemon]:
    result = [pokemon for pokemon in player.active if pokemon is not None]
    result.extend(player.bench)
    return result


def _field_counts(player) -> defaultdict[int, int]:
    counts: defaultdict[int, int] = defaultdict(int)
    for pokemon in _all_in_play(player):
        counts[pokemon.id] += 1
    return counts


def _line_count(field_counts: dict[int, int], line: tuple[int, ...]) -> int:
    return sum(field_counts[card_id] for card_id in line)


def _desired_dragon_lines(opponent_prizes: int) -> int:
    if opponent_prizes >= 5:
        return 3
    if opponent_prizes >= 3:
        return 2
    return 1


def _unseen_counts(obs: Observation, my_index: int) -> defaultdict[int, int]:
    """公開領域にない自分のカード枚数。山札とサイドの合計として扱う。"""
    counts: defaultdict[int, int] = defaultdict(int, deck_total)
    player = obs.current.players[my_index]
    seen_serials: set[int] = set()

    def consume(card: Card | Pokemon | None) -> None:
        if card is None or card.serial in seen_serials:
            return
        seen_serials.add(card.serial)
        counts[card.id] -= 1
        if isinstance(card, Pokemon):
            for attached in card.energyCards:
                consume(attached)
            for tool in card.tools:
                consume(tool)
            for previous in card.preEvolution:
                consume(previous)

    for card in player.hand or []:
        consume(card)
    for card in player.discard:
        consume(card)
    for card in _all_in_play(player):
        consume(card)
    for card in obs.current.stadium:
        if card.playerIndex == my_index:
            consume(card)
    if obs.current.looking is not None:
        for card in obs.current.looking:
            if card is not None and card.playerIndex == my_index:
                consume(card)

    for card_id in list(counts):
        counts[card_id] = max(0, counts[card_id])
    return counts


def _prize_count(pokemon: Pokemon) -> int:
    data = card_table[pokemon.id]
    if data.megaEx:
        return 3
    if data.ex:
        return 2
    return 1


def _damage(
    attack_id: int,
    attacker: Pokemon,
    target: Pokemon,
    roserade_count: int,
    power_pro_used: bool,
) -> int:
    damage = attack_table[attack_id].damage
    if attacker.id in CYNTHIAS_POKEMON:
        damage += roserade_count * 30
    attacker_type = card_table[attacker.id].energyType
    if power_pro_used and attacker_type == EnergyType.FIGHTING:
        damage += 30

    target_data = card_table[target.id]
    if target_data.weakness == attacker_type:
        damage *= 2
    elif target_data.resistance == attacker_type:
        damage -= 30
    return max(0, damage)


def _available_attack_ids(pokemon: Pokemon | None) -> list[int]:
    if pokemon is None:
        return []
    energy_count = len(pokemon.energies)
    if pokemon.id == CYNTHIAS_GARCHOMP_EX:
        attacks = []
        if energy_count >= 1:
            attacks.append(SCREW_DIVE)
        if energy_count >= 2:
            attacks.append(DRACONIC_BUSTER)
        return attacks
    if pokemon.id in {CYNTHIAS_GIBLE, CYNTHIAS_GABITE} and energy_count >= 1:
        return list(card_table[pokemon.id].attacks)
    if pokemon.id == CYNTHIAS_ROSERADE and energy_count >= 3:
        return list(card_table[pokemon.id].attacks)
    if pokemon.id == CYNTHIAS_ROSELIA and energy_count >= 1:
        return list(card_table[pokemon.id].attacks)
    return []


def _max_damage(
    attacker: Pokemon | None,
    target: Pokemon | None,
    roserade_count: int,
    power_pro_used: bool,
) -> int:
    if attacker is None or target is None:
        return 0
    return max(
        (
            _damage(attack_id, attacker, target, roserade_count, power_pro_used)
            for attack_id in _available_attack_ids(attacker)
        ),
        default=0,
    )


def _estimated_attack_pressure(
    pokemon: Pokemon,
    my_active: Pokemon | None,
    opponent_prizes: int,
) -> int:
    data = card_table[pokemon.id]
    attack_damages = [attack_table[attack_id].damage for attack_id in data.attacks]
    max_attack_damage = max(attack_damages, default=0)
    energy_count = len(pokemon.energies)

    score = 0
    if data.megaEx:
        score += 1800
    elif data.ex:
        score += 1200
    score += 900 if data.stage2 else 500 if data.stage1 else 0
    score += energy_count * 420 + len(pokemon.tools) * 160
    if energy_count > 0:
        score += min(max_attack_damage, 330) * 7
    if energy_count >= 2:
        score += 500

    if my_active is not None and max_attack_damage > 0:
        my_active_prizes = _prize_count(my_active)
        if max_attack_damage >= my_active.hp:
            score += 2400
            if my_active_prizes >= opponent_prizes:
                score += 9000
        else:
            score += int(900 * max_attack_damage / max(1, my_active.hp))
    return score


def _target_score(
    pokemon: Pokemon,
    damage: int,
    my_prizes: int,
    opponent_prizes: int,
    my_active: Pokemon | None,
) -> int:
    data = card_table[pokemon.id]
    prizes = _prize_count(pokemon)
    score = prizes * 1500 + len(pokemon.energies) * 180 + len(pokemon.tools) * 80
    score += 300 if data.stage2 else 150 if data.stage1 else 0
    score += min(pokemon.hp, 350)
    score += _estimated_attack_pressure(pokemon, my_active, opponent_prizes)
    if damage >= pokemon.hp:
        score += 6500 + prizes * 2200
        if prizes >= my_prizes:
            score += 60000
        elif my_prizes <= 2:
            score += prizes * 2500
    elif damage > 0:
        score += int(1600 * damage / max(1, pokemon.hp))
        if my_prizes <= 2 and prizes >= my_prizes:
            score += 1200
    return score


def _boss_is_useful(
    my_active: Pokemon | None,
    opponent,
    my_prizes: int,
    opponent_prizes: int,
    roserade_count: int,
    power_pro_used: bool,
) -> bool:
    if my_active is None or not opponent.bench or not _available_attack_ids(my_active):
        return False
    opponent_active = opponent.active[0] if opponent.active else None
    if opponent_active is None:
        return False
    active_damage = _max_damage(
        my_active, opponent_active, roserade_count, power_pro_used
    )
    active_knockout = active_damage >= opponent_active.hp
    active_prizes = _prize_count(opponent_active) if active_knockout else 0
    for pokemon in opponent.bench:
        damage = _max_damage(my_active, pokemon, roserade_count, power_pro_used)
        if damage < pokemon.hp:
            continue
        prizes = _prize_count(pokemon)
        if prizes >= my_prizes or not active_knockout or prizes > active_prizes:
            return True
    return False


def _lillie_score(
    my_state, field_counts: dict[int, int], hand_counts: dict[int, int]
) -> int:
    dragon_count = _line_count(
        field_counts,
        (CYNTHIAS_GIBLE, CYNTHIAS_GABITE, CYNTHIAS_GARCHOMP_EX),
    )
    has_progress_card = bool(
        hand_counts[CYNTHIAS_GIBLE]
        or hand_counts[BUDDY_BUDDY_POFFIN]
        or hand_counts[POKE_PAD]
        or hand_counts[FIGHTING_GONG]
        or hand_counts[HILDA]
        or (
            field_counts[CYNTHIAS_GIBLE]
            and (hand_counts[CYNTHIAS_GABITE] or hand_counts[CYNTHIAS_GARCHOMP_EX])
        )
        or (field_counts[CYNTHIAS_ROSELIA] and hand_counts[CYNTHIAS_ROSERADE])
    )
    weak_hand = my_state.handCount <= 3 or (dragon_count < 3 and not has_progress_card)
    if len(my_state.prize) == 6:
        return 110000 if weak_hand else 90000
    if weak_hand:
        return 104000
    return 90000 if my_state.handCount <= 5 else 30000


def _to_bench_score(
    card_id: int,
    effect_id: int,
    occurrence: int,
    field_counts: dict[int, int],
    dragon_target: int,
) -> int:
    dragon_count = _line_count(
        field_counts,
        (CYNTHIAS_GIBLE, CYNTHIAS_GABITE, CYNTHIAS_GARCHOMP_EX),
    )
    rose_count = _line_count(field_counts, (CYNTHIAS_ROSELIA, CYNTHIAS_ROSERADE))
    if effect_id == BUDDY_BUDDY_POFFIN:
        missing_dragons = max(0, dragon_target - dragon_count)
        missing_roses = max(0, 2 - rose_count)
        if card_id == CYNTHIAS_GIBLE:
            return (
                110000 - occurrence * 2000
                if occurrence < missing_dragons
                else 70000 - occurrence * 2000
            )
        if card_id == CYNTHIAS_ROSELIA:
            return (
                105000 - occurrence * 2000
                if occurrence < missing_roses
                else 68000 - occurrence * 2000
            )
        return -1
    score = (
        100000
        if card_id == CYNTHIAS_GIBLE and dragon_count < dragon_target
        else 97000 if card_id == CYNTHIAS_ROSELIA and rose_count < 3 else -1
    )
    return score - occurrence * 7000


def _hand_value(
    card_id: int,
    field_counts: dict[int, int],
    hand_counts: dict[int, int],
    discard_counts: dict[int, int],
) -> int:
    dragon_count = _line_count(
        field_counts,
        (CYNTHIAS_GIBLE, CYNTHIAS_GABITE, CYNTHIAS_GARCHOMP_EX),
    )
    rose_count = _line_count(field_counts, (CYNTHIAS_ROSELIA, CYNTHIAS_ROSERADE))
    if card_id == CYNTHIAS_GARCHOMP_EX:
        return 9000 if field_counts[CYNTHIAS_GABITE] else 3500
    if card_id == CYNTHIAS_GABITE:
        return 8500 if field_counts[CYNTHIAS_GIBLE] else 3000
    if card_id == CYNTHIAS_GIBLE:
        return 7000 if dragon_count < 3 else 1200
    if card_id == CYNTHIAS_ROSERADE:
        return 8000 if field_counts[CYNTHIAS_ROSELIA] else 2500
    if card_id == CYNTHIAS_ROSELIA:
        return 6500 if rose_count < 3 else 1000
    if card_id in ENERGY_IDS:
        return 4500 if hand_counts[card_id] <= 1 else 1800
    if card_id == NIGHT_STRETCHER:
        useful = any(
            discard_counts[candidate] > 0
            for candidate in CYNTHIAS_POKEMON | {BASIC_FIGHTING_ENERGY}
        )
        return 5500 if useful else 1000
    if card_id == RARE_CANDY:
        combo_ready = (
            field_counts[CYNTHIAS_GIBLE] > 0 and hand_counts[CYNTHIAS_GARCHOMP_EX] > 0
        )
        return 9500 if combo_ready else 3000
    if card_id == HILDA:
        evolution_ready = (
            field_counts[CYNTHIAS_GIBLE]
            or field_counts[CYNTHIAS_GABITE]
            or field_counts[CYNTHIAS_ROSELIA]
        )
        needs_energy = not any(hand_counts[energy_id] for energy_id in ENERGY_IDS)
        return 9000 if evolution_ready and needs_energy else 6500
    if card_id in {LILLIES_DETERMINATION, UNFAIR_STAMP}:
        return 5000
    if card_id == FOREST_OF_VITALITY:
        return 4000 if field_counts[CYNTHIAS_ROSELIA] else 800
    return 500 if hand_counts[card_id] >= 2 else 2500


def _search_score(
    card: Card | Pokemon,
    effect_id: int,
    field_counts: dict[int, int],
    hand_counts: dict[int, int],
    discard_counts: dict[int, int],
    my_state,
    opponent,
    stadium_id: int,
) -> int:
    card_id = card.id
    dragon_count = _line_count(
        field_counts,
        (CYNTHIAS_GIBLE, CYNTHIAS_GABITE, CYNTHIAS_GARCHOMP_EX),
    )
    dragon_target = _desired_dragon_lines(len(opponent.prize))
    rose_count = _line_count(field_counts, (CYNTHIAS_ROSELIA, CYNTHIAS_ROSERADE))
    mature_gible_count = sum(
        pokemon.id == CYNTHIAS_GIBLE and not pokemon.appearThisTurn
        for pokemon in _all_in_play(my_state)
    )
    mature_gible = mature_gible_count > 0
    mature_gabite = any(
        pokemon.id == CYNTHIAS_GABITE and not pokemon.appearThisTurn
        for pokemon in _all_in_play(my_state)
    )
    mature_roselia = any(
        pokemon.id == CYNTHIAS_ROSELIA and not pokemon.appearThisTurn
        for pokemon in _all_in_play(my_state)
    )
    bench_space = my_state.benchMax - len(my_state.bench)
    need_gible = (
        bench_space > 0
        and dragon_count < dragon_target
        and hand_counts[CYNTHIAS_GIBLE] == 0
    )
    need_roselia = (
        bench_space > 0 and rose_count < 2 and hand_counts[CYNTHIAS_ROSELIA] == 0
    )
    first_garchomp_missing = field_counts[CYNTHIAS_GARCHOMP_EX] == 0
    first_roserade_missing = field_counts[CYNTHIAS_ROSERADE] == 0

    if effect_id == CYNTHIAS_GABITE:
        need_garchomp = (
            field_counts[CYNTHIAS_GARCHOMP_EX] < dragon_target
            and hand_counts[CYNTHIAS_GARCHOMP_EX] == 0
        )
        energy_in_hand = any(hand_counts[energy_id] for energy_id in ENERGY_IDS)
        mature_gabite_can_attack = any(
            pokemon.id == CYNTHIAS_GABITE
            and not pokemon.appearThisTurn
            and (pokemon.energies or energy_in_hand)
            for pokemon in _all_in_play(my_state)
        )
        candy_garchomp_can_attack = bool(
            mature_gible and hand_counts[RARE_CANDY] and energy_in_hand
        )
        need_garchomp_for_attack = need_garchomp and (
            mature_gabite_can_attack or candy_garchomp_can_attack
        )
        cannot_evolve_garchomp = field_counts[CYNTHIAS_GABITE] > 0 and not mature_gabite
        needs_gabite_for_field = hand_counts[CYNTHIAS_GABITE] < mature_gible_count
        needs_roserade_for_field = (
            hand_counts[CYNTHIAS_ROSERADE] < field_counts[CYNTHIAS_ROSELIA]
        )
        priorities = {
            CYNTHIAS_GARCHOMP_EX: (
                126000
                if need_garchomp_for_attack
                else 70000 if need_garchomp else 52000
            ),
            CYNTHIAS_GABITE: (
                130000
                if mature_gible and needs_gabite_for_field
                else 96000 if dragon_count < dragon_target else 65000
            ),
            CYNTHIAS_ROSERADE: (
                112000
                if needs_roserade_for_field
                else 88000 if field_counts[CYNTHIAS_ROSELIA] else 62000
            ),
            CYNTHIAS_GIBLE: (
                121000
                if cannot_evolve_garchomp and need_gible
                else (
                    106000
                    if need_gible
                    else 50000 if dragon_count < dragon_target else 25000
                )
            ),
            CYNTHIAS_ROSELIA: (
                118000
                if cannot_evolve_garchomp and need_roselia
                else 102000 if need_roselia else 45000 if rose_count < 3 else 22000
            ),
        }
        return priorities.get(card_id, 0)

    if effect_id == POKE_PAD:
        gible_basics = field_counts[CYNTHIAS_GIBLE] + hand_counts[CYNTHIAS_GIBLE]
        roselia_basics = field_counts[CYNTHIAS_ROSELIA] + hand_counts[CYNTHIAS_ROSELIA]
        planned_dragon_count = dragon_count + min(
            hand_counts[CYNTHIAS_GIBLE], bench_space
        )
        dragon_setup_needed = (
            planned_dragon_count < dragon_target
            and bench_space > hand_counts[CYNTHIAS_GIBLE]
        )
        can_get_gabite_next_turn = bool(
            hand_counts[HILDA] or hand_counts[POKE_PAD] or field_counts[CYNTHIAS_GABITE]
        )
        reserve_gabite = (
            hand_counts[CYNTHIAS_GABITE] == 0
            and not can_get_gabite_next_turn
            and (field_counts[CYNTHIAS_GIBLE] or hand_counts[CYNTHIAS_GIBLE])
        )
        backup_roselia_needed = (
            bench_space > 0
            and roselia_basics < 2
            and field_counts[CYNTHIAS_ROSERADE] > 0
        )
        needs_gabite_for_field = (
            hand_counts[CYNTHIAS_GABITE] < field_counts[CYNTHIAS_GIBLE]
        )
        needs_roserade_for_field = (
            hand_counts[CYNTHIAS_ROSERADE] < field_counts[CYNTHIAS_ROSELIA]
        )
        priorities = {
            CYNTHIAS_GIBLE: (
                120000
                if dragon_setup_needed and (not reserve_gabite or gible_basics == 0)
                else 112000 if dragon_setup_needed else 25000
            ),
            CYNTHIAS_ROSELIA: (
                96000
                if not dragon_setup_needed and roselia_basics == 0
                else (
                    90000
                    if not dragon_setup_needed and backup_roselia_needed
                    else 20000
                )
            ),
            CYNTHIAS_GABITE: (
                124000
                if mature_gible and first_garchomp_missing and needs_gabite_for_field
                else (
                    116000
                    if reserve_gabite
                    else 104000 if mature_gible and needs_gabite_for_field else 18000
                )
            ),
            CYNTHIAS_ROSERADE: (
                104000
                if mature_roselia
                and needs_roserade_for_field
                and first_roserade_missing
                and not dragon_setup_needed
                else (
                    88000
                    if mature_roselia
                    and needs_roserade_for_field
                    and not dragon_setup_needed
                    else 16000
                )
            ),
        }
        return priorities.get(card_id, 0)

    if effect_id == HILDA:
        priorities = {
            CYNTHIAS_GARCHOMP_EX: (
                124000
                if mature_gabite
                and field_counts[CYNTHIAS_GARCHOMP_EX] < dragon_target
                and hand_counts[CYNTHIAS_GARCHOMP_EX] == 0
                else (
                    92000
                    if field_counts[CYNTHIAS_GABITE]
                    and field_counts[CYNTHIAS_GARCHOMP_EX] < dragon_target
                    else 30000
                )
            ),
            CYNTHIAS_GABITE: (
                118000
                if mature_gible and hand_counts[CYNTHIAS_GABITE] == 0
                else 88000 if field_counts[CYNTHIAS_GIBLE] else 56000
            ),
            CYNTHIAS_ROSERADE: (
                112000
                if field_counts[CYNTHIAS_ROSELIA]
                and hand_counts[CYNTHIAS_ROSERADE] == 0
                else 82000 if field_counts[CYNTHIAS_ROSELIA] else 52000
            ),
            BASIC_FIGHTING_ENERGY: (
                110000 if hand_counts[BASIC_FIGHTING_ENERGY] == 0 else 98000
            ),
            ROCK_FIGHTING_ENERGY: (
                106000
                if not any(hand_counts[energy_id] for energy_id in ENERGY_IDS)
                else 94000
            ),
        }
        return priorities.get(card_id, -1)

    if effect_id == FIGHTING_GONG:
        if card_id == CYNTHIAS_GIBLE:
            return (
                92000
                if dragon_count < dragon_target
                and len(my_state.bench) < my_state.benchMax
                else 30000
            )
        if card_id == BASIC_FIGHTING_ENERGY:
            no_energy = not any(hand_counts[energy_id] for energy_id in ENERGY_IDS)
            return 90000 if no_energy else 72000

    if effect_id == NIGHT_STRETCHER:
        priorities = {
            CYNTHIAS_GARCHOMP_EX: (
                110000
                if field_counts[CYNTHIAS_GABITE] and first_garchomp_missing
                else 92000 if field_counts[CYNTHIAS_GABITE] else 45000
            ),
            CYNTHIAS_GABITE: (
                106000
                if field_counts[CYNTHIAS_GIBLE] and first_garchomp_missing
                else 90000 if field_counts[CYNTHIAS_GIBLE] else 40000
            ),
            CYNTHIAS_ROSERADE: (
                102000
                if field_counts[CYNTHIAS_ROSELIA] and first_roserade_missing
                else 88000 if field_counts[CYNTHIAS_ROSELIA] else 38000
            ),
            CYNTHIAS_GIBLE: (
                108000
                if need_gible
                and (
                    field_counts[CYNTHIAS_GABITE]
                    or field_counts[CYNTHIAS_GARCHOMP_EX]
                    or hand_counts[CYNTHIAS_GABITE]
                    or hand_counts[CYNTHIAS_GARCHOMP_EX]
                )
                else 98000 if need_gible else 25000
            ),
            CYNTHIAS_ROSELIA: (
                104000
                if need_roselia
                and (field_counts[CYNTHIAS_ROSERADE] or hand_counts[CYNTHIAS_ROSERADE])
                else 94000 if need_roselia else 20000
            ),
            BASIC_FIGHTING_ENERGY: 70000,
        }
        return priorities.get(card_id, 0)

    if effect_id == POKEGEAR_3_0:
        if card_id == HILDA:
            needs_energy = not any(hand_counts[energy_id] for energy_id in ENERGY_IDS)
            return 102000 if needs_energy else 76000
        if card_id == BOSSS_ORDERS:
            active = my_state.active[0] if my_state.active else None
            return (
                96000
                if _boss_is_useful(
                    active,
                    opponent,
                    len(my_state.prize),
                    len(opponent.prize),
                    field_counts[CYNTHIAS_ROSERADE],
                    premium_used,
                )
                else 20000
            )
        if card_id == LILLIES_DETERMINATION:
            return _lillie_score(my_state, field_counts, hand_counts)
        if card_id == TEAM_ROCKETS_PETREL:
            return 78000 if dragon_count < 2 else 50000
        if card_id == JUDGE:
            return (
                76000 if opponent.handCount >= 6 and my_state.handCount <= 4 else 30000
            )

    if effect_id == TEAM_ROCKETS_PETREL:
        if card_id == RARE_CANDY:
            return (
                104000 if mature_gible and hand_counts[CYNTHIAS_GARCHOMP_EX] else 55000
            )
        if card_id == BUDDY_BUDDY_POFFIN:
            return (
                100000
                if bench_space >= 2 and (dragon_count < 2 or rose_count < 2)
                else 45000
            )
        if card_id == POKE_PAD:
            return (
                104000
                if field_counts[CYNTHIAS_GIBLE] or field_counts[CYNTHIAS_ROSELIA]
                else 65000
            )
        if card_id == NIGHT_STRETCHER:
            useful = any(
                discard_counts[candidate] > 0
                for candidate in CYNTHIAS_POKEMON | {BASIC_FIGHTING_ENERGY}
            )
            return 98000 if useful else 35000
        if card_id == FOREST_OF_VITALITY:
            return (
                93000
                if stadium_id != FOREST_OF_VITALITY and field_counts[CYNTHIAS_ROSELIA]
                else 40000
            )
        if card_id == FIGHTING_GONG:
            return (
                90000
                if dragon_count < 2 or not any(hand_counts[e] for e in ENERGY_IDS)
                else 60000
            )
        if card_id == CYNTHIAS_POWER_WEIGHT:
            return 70000 if field_counts[CYNTHIAS_GARCHOMP_EX] else 45000
        if card_id == PREMIUM_POWER_PRO:
            return 50000
        if card_id == POKEGEAR_3_0:
            has_supporter = any(
                hand_counts[supporter] > 0 for supporter in SUPPORTER_IDS
            )
            return 62000 if not has_supporter else 30000

    priorities = {
        CYNTHIAS_GARCHOMP_EX: 90000 if field_counts[CYNTHIAS_GABITE] else 50000,
        CYNTHIAS_GABITE: 85000 if field_counts[CYNTHIAS_GIBLE] else 45000,
        CYNTHIAS_ROSERADE: 80000 if field_counts[CYNTHIAS_ROSELIA] else 40000,
        CYNTHIAS_GIBLE: 74000 if dragon_count < dragon_target else 20000,
        CYNTHIAS_ROSELIA: 70000 if rose_count < 3 else 18000,
        BASIC_FIGHTING_ENERGY: 60000,
        ROCK_FIGHTING_ENERGY: 60000,
    }
    return priorities.get(
        card_id, _hand_value(card_id, field_counts, hand_counts, discard_counts)
    )


def _attach_score(
    card: Card,
    pokemon: Pokemon,
    is_active: bool,
    my_state,
    opponent,
    roserade_count: int,
) -> int:
    opponent_field_ids = {target.id for target in _all_in_play(opponent)}
    bench_pressure = bool(opponent_field_ids & {119, 120, 121, 1030, 1031})
    ready_garchomp_count = sum(
        target.id == CYNTHIAS_GARCHOMP_EX and len(target.energies) >= 1
        for target in _all_in_play(my_state)
    )

    if card_table[card.id].cardType == CardType.TOOL:
        if card.id != CYNTHIAS_POWER_WEIGHT:
            return 30000
        if (
            bench_pressure
            and pokemon.id in {CYNTHIAS_GIBLE, CYNTHIAS_GABITE}
            and ready_garchomp_count < 2
        ):
            return 96000
        if pokemon.id == CYNTHIAS_GARCHOMP_EX:
            return 92000 if is_active else 88000
        if pokemon.id == CYNTHIAS_GABITE:
            return 82000
        return 65000 if pokemon.id in CYNTHIAS_POKEMON else -1

    energy_count = len(pokemon.energies)
    rock_bonus = 600 if card.id == ROCK_FIGHTING_ENERGY else 0
    active = my_state.active[0] if my_state.active else None
    active_needs_energy = active is not None and not _available_attack_ids(active)
    if (
        card.id == ROCK_FIGHTING_ENERGY
        and opponent_field_ids & {119, 120, 121, 235}
        and (is_active or not active_needs_energy)
        and pokemon.id
        in {
            CYNTHIAS_GIBLE,
            CYNTHIAS_GABITE,
            CYNTHIAS_ROSELIA,
            CYNTHIAS_ROSERADE,
        }
    ):
        rock_bonus += 8000
    opponent_active = opponent.active[0] if opponent.active else None
    if pokemon.id == CYNTHIAS_GARCHOMP_EX:
        if energy_count == 0:
            return (98000 if is_active else 92000) + rock_bonus
        if energy_count == 1:
            dive_damage = (
                _damage(
                    SCREW_DIVE, pokemon, opponent_active, roserade_count, premium_used
                )
                if opponent_active is not None
                else 0
            )
            buster_damage = (
                _damage(
                    DRACONIC_BUSTER,
                    pokemon,
                    opponent_active,
                    roserade_count,
                    premium_used,
                )
                if opponent_active is not None
                else 0
            )
            needs_buster = (
                opponent_active is not None
                and dive_damage < opponent_active.hp <= buster_damage
            )
            if is_active and needs_buster:
                return 94000 + rock_bonus
            return (79000 if not is_active else 68000) + rock_bonus
        return -1
    if pokemon.id == CYNTHIAS_GABITE and energy_count == 0:
        base = 76000 if is_active else 87000 if ready_garchomp_count else 70000
        return base + rock_bonus
    if pokemon.id == CYNTHIAS_GIBLE and energy_count == 0:
        base = 73000 if is_active else 84000 if ready_garchomp_count else 67000
        return base + rock_bonus
    if pokemon.id == CYNTHIAS_ROSELIA and energy_count == 0:
        if is_active and not ready_garchomp_count:
            return 76000 + rock_bonus
        if is_active:
            return 64000 + rock_bonus
        return -1
    if pokemon.id == CYNTHIAS_ROSERADE and energy_count == 0:
        if is_active and not ready_garchomp_count:
            return 62000 + rock_bonus
        if is_active:
            return 52000 + rock_bonus
        return -1
    return -1


def _play_score(
    card: Card,
    obs: Observation,
    field_counts: dict[int, int],
    hand_counts: dict[int, int],
    discard_counts: dict[int, int],
    unseen_counts: dict[int, int],
    stadium_id: int,
    roserade_count: int,
) -> int:
    state = obs.current
    my_state = state.players[state.yourIndex]
    opponent = state.players[1 - state.yourIndex]
    active = my_state.active[0] if my_state.active else None
    card_id = card.id
    dragon_count = _line_count(
        field_counts,
        (CYNTHIAS_GIBLE, CYNTHIAS_GABITE, CYNTHIAS_GARCHOMP_EX),
    )
    dragon_target = _desired_dragon_lines(len(opponent.prize))
    rose_count = _line_count(field_counts, (CYNTHIAS_ROSELIA, CYNTHIAS_ROSERADE))
    bench_space = my_state.benchMax - len(my_state.bench)

    if card_id == CYNTHIAS_GIBLE:
        return 101000 if dragon_count < dragon_target else -1
    if card_id == CYNTHIAS_ROSELIA:
        return 98000 if rose_count < 3 else -1
    if card_id == RARE_CANDY:
        mature_gible = any(
            target.id == CYNTHIAS_GIBLE and not target.appearThisTurn
            for target in _all_in_play(my_state)
        )
        return (
            116000
            if mature_gible
            and field_counts[CYNTHIAS_GARCHOMP_EX] < dragon_target
            and hand_counts[CYNTHIAS_GARCHOMP_EX] > 0
            else -1
        )
    if card_id == BUDDY_BUDDY_POFFIN:
        useful_basics = (
            unseen_counts[CYNTHIAS_GIBLE] if dragon_count < dragon_target else 0
        ) + (unseen_counts[CYNTHIAS_ROSELIA] if rose_count < 3 else 0)
        return 108000 if bench_space > 0 and useful_basics > 0 else -1
    if card_id == POKE_PAD:
        useful = (
            (
                field_counts[CYNTHIAS_GIBLE] > hand_counts[CYNTHIAS_GABITE]
                and unseen_counts[CYNTHIAS_GABITE]
            )
            or (
                field_counts[CYNTHIAS_ROSELIA] > hand_counts[CYNTHIAS_ROSERADE]
                and unseen_counts[CYNTHIAS_ROSERADE]
            )
            or (dragon_count < dragon_target and unseen_counts[CYNTHIAS_GIBLE])
        )
        return 104000 if useful else -1
    if card_id == FIGHTING_GONG:
        need_energy = not any(hand_counts[energy_id] for energy_id in ENERGY_IDS)
        return (
            96000
            if need_energy or (dragon_count < dragon_target and bench_space > 0)
            else 50000
        )
    if card_id == FOREST_OF_VITALITY:
        if stadium_id == FOREST_OF_VITALITY:
            return -1
        if field_counts[CYNTHIAS_ROSELIA] or hand_counts[CYNTHIAS_ROSELIA]:
            return 106000
        return 30000 if stadium_id else -1
    if card_id == NIGHT_STRETCHER:
        useful = any(
            discard_counts[candidate] > 0
            for candidate in CYNTHIAS_POKEMON | {BASIC_FIGHTING_ENERGY}
        )
        return 86000 if useful else -1
    if card_id == POKEGEAR_3_0:
        has_supporter = any(hand_counts[supporter] > 0 for supporter in SUPPORTER_IDS)
        return 72000 if not state.supporterPlayed and not has_supporter else 35000
    if card_id == UNFAIR_STAMP:
        return 97000
    if card_id == PREMIUM_POWER_PRO:
        if active is None or card_table[active.id].energyType != EnergyType.FIGHTING:
            return -1
        opponent_active = opponent.active[0] if opponent.active else None
        if opponent_active is None:
            return -1
        attacks = _available_attack_ids(active)
        without = max(
            (
                _damage(a, active, opponent_active, roserade_count, False)
                for a in attacks
            ),
            default=0,
        )
        with_pro = max(
            (
                _damage(a, active, opponent_active, roserade_count, True)
                for a in attacks
            ),
            default=0,
        )
        if without < opponent_active.hp <= with_pro:
            return 103000
        return 42000 if attacks and len(opponent.prize) <= 2 else -1
    if card_id == HILDA:
        has_immediate_evolution = (
            (field_counts[CYNTHIAS_GABITE] and unseen_counts[CYNTHIAS_GARCHOMP_EX] > 0)
            or (field_counts[CYNTHIAS_GIBLE] and unseen_counts[CYNTHIAS_GABITE] > 0)
            or (field_counts[CYNTHIAS_ROSELIA] and unseen_counts[CYNTHIAS_ROSERADE] > 0)
        )
        has_evolution_target = any(
            unseen_counts[target_id] > 0
            for target_id in {
                CYNTHIAS_GARCHOMP_EX,
                CYNTHIAS_GABITE,
                CYNTHIAS_ROSERADE,
            }
        )
        has_energy_target = any(
            unseen_counts[energy_id] > 0 for energy_id in ENERGY_IDS
        )
        if not has_evolution_target or not has_energy_target:
            return -1
        needs_energy = not any(hand_counts[energy_id] for energy_id in ENERGY_IDS)
        if needs_energy:
            return 109000
        return 90000 if has_immediate_evolution else 62000
    if card_id == BOSSS_ORDERS:
        return (
            90000
            if _boss_is_useful(
                active,
                opponent,
                len(my_state.prize),
                len(opponent.prize),
                roserade_count,
                premium_used,
            )
            else -1
        )
    if card_id == LILLIES_DETERMINATION:
        return _lillie_score(my_state, field_counts, hand_counts)
    if card_id == JUDGE:
        return 68000 if opponent.handCount >= 6 and my_state.handCount <= 4 else -1
    if card_id == TEAM_ROCKETS_PETREL:
        setup_needed = dragon_count < 2 or (
            field_counts[CYNTHIAS_GIBLE] and not hand_counts[CYNTHIAS_GABITE]
        )
        return 64000 if setup_needed else 38000
    return -1


def _evolve_score(obs: Observation, option, field_counts: dict[int, int]) -> int:
    source = get_card(
        obs,
        option.inPlayArea,
        option.inPlayIndex,
        obs.current.yourIndex,
    )
    evolution = get_card(
        obs,
        option.area,
        option.index,
        obs.current.yourIndex,
    )
    if not isinstance(source, Pokemon):
        return 0
    opponent = obs.current.players[1 - obs.current.yourIndex]
    dragon_target = _desired_dragon_lines(len(opponent.prize))
    if source.id == CYNTHIAS_GIBLE:
        if evolution is not None and evolution.id == CYNTHIAS_GARCHOMP_EX:
            if field_counts[CYNTHIAS_GARCHOMP_EX] >= dragon_target:
                return 12000
            return 119000
        return 114000
    if source.id == CYNTHIAS_ROSELIA:
        is_active = option.inPlayArea == AreaType.ACTIVE
        my_state = obs.current.players[obs.current.yourIndex]
        if not is_active:
            active_is_roselia = bool(
                my_state.active and my_state.active[0].id == CYNTHIAS_ROSELIA
            )
            return 113000 if active_is_roselia else 109000
        if len(source.energies) >= 3:
            return 112000
        bench_can_attack = any(
            _available_attack_ids(pokemon) for pokemon in my_state.bench
        )
        if _available_attack_ids(source) and not bench_can_attack:
            return 25000
        return 111000 if not _available_attack_ids(source) else 107000
    if source.id == CYNTHIAS_GABITE:
        if field_counts[CYNTHIAS_GARCHOMP_EX] < dragon_target:
            return 116000
        if option.inPlayArea == AreaType.ACTIVE:
            return 94000
        return 12000
    return 0


def _attack_score(
    attack_id: int,
    my_active: Pokemon | None,
    opponent_active: Pokemon | None,
    roserade_count: int,
    opponent_prizes: int,
    backup_ready: bool,
    energy_in_hand: bool,
) -> int:
    if my_active is None or opponent_active is None:
        return attack_id
    damage = _damage(
        attack_id, my_active, opponent_active, roserade_count, premium_used
    )
    knockout = damage >= opponent_active.hp
    prizes = _prize_count(opponent_active)
    if attack_id == SCREW_DIVE:
        return 32200 + (12000 + prizes * 2500 if knockout else 0)
    if attack_id == DRACONIC_BUSTER:
        dive_damage = _damage(
            SCREW_DIVE, my_active, opponent_active, roserade_count, premium_used
        )
        if knockout and dive_damage < opponent_active.hp:
            score = 47000 + prizes * 3000
            if prizes >= opponent_prizes:
                return score + 50000
            if not backup_ready and not energy_in_hand:
                score -= 6000
            return score
        return 38000 + prizes * 2000 if knockout else 28000
    return 30000 + (10000 + prizes * 2000 if knockout else 0)


def agent(obs_dict: dict) -> list[int]:
    """現在の選択肢をヒューリスティックで評価して返す。"""
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    state = obs.current
    select = obs.select
    my_index = state.yourIndex
    my_state = state.players[my_index]
    opponent = state.players[1 - my_index]
    context = select.context

    global premium_turn
    global premium_used
    if premium_turn != state.turn:
        premium_turn = state.turn
        premium_used = False
    for log in obs.logs:
        if log.playerIndex == my_index and log.cardId == PREMIUM_POWER_PRO:
            premium_used = True

    field_counts = _field_counts(my_state)
    hand_counts: defaultdict[int, int] = defaultdict(int)
    for card in my_state.hand or []:
        hand_counts[card.id] += 1
    discard_counts: defaultdict[int, int] = defaultdict(int)
    for card in my_state.discard:
        discard_counts[card.id] += 1
    unseen_counts = _unseen_counts(obs, my_index)

    active = my_state.active[0] if my_state.active else None
    opponent_active = opponent.active[0] if opponent.active else None
    roserade_count = field_counts[CYNTHIAS_ROSERADE]
    dragon_target = _desired_dragon_lines(len(opponent.prize))
    stadium_id = state.stadium[0].id if state.stadium else 0
    effect_id = (
        select.effect.id
        if select.effect is not None
        else select.contextCard.id if select.contextCard is not None else 0
    )
    bench_ready = any(
        pokemon.id == CYNTHIAS_GARCHOMP_EX and len(pokemon.energies) >= 1
        for pokemon in my_state.bench
    )
    energy_in_hand = any(hand_counts[energy_id] > 0 for energy_id in ENERGY_IDS)
    active_ready = bool(_available_attack_ids(active))
    active_damage = _max_damage(active, opponent_active, roserade_count, premium_used)
    bench_attack_damage = max(
        (
            _max_damage(pokemon, opponent_active, roserade_count, premium_used)
            for pokemon in my_state.bench
        ),
        default=0,
    )
    scores: list[int] = []
    option_occurrence: defaultdict[int, int] = defaultdict(int)

    for option in select.option:
        score = 0
        if option.type == OptionType.NUMBER:
            score = option.number or 0
        elif option.type == OptionType.YES:
            if context == SelectContext.IS_FIRST:
                score = 100
            elif (
                context == SelectContext.ACTIVATE and effect_id == CYNTHIAS_GARCHOMP_EX
            ):
                score = 10 if my_state.handCount < 6 and my_state.deckCount > 3 else -1
            else:
                score = 1
        elif option.type == OptionType.NO:
            score = 0
        elif option.type == OptionType.CARD:
            card = get_card(obs, option.area, option.index, option.playerIndex)
            if card is None:
                score = -1
            elif context in {
                SelectContext.SETUP_ACTIVE_POKEMON,
                SelectContext.TO_ACTIVE,
                SelectContext.SWITCH,
            }:
                if option.playerIndex == my_index:
                    if context == SelectContext.SETUP_ACTIVE_POKEMON:
                        score = (
                            100000
                            if card.id == CYNTHIAS_GIBLE
                            else 85000 if card.id == CYNTHIAS_ROSELIA else 1000
                        )
                    elif isinstance(card, Pokemon):
                        if card.id == CYNTHIAS_GARCHOMP_EX:
                            score = 100000 + len(card.energies) * 5000 + card.hp
                        elif card.id == CYNTHIAS_GABITE:
                            score = 50000 + len(card.energies) * 4000 + card.hp
                        elif card.id == CYNTHIAS_GIBLE:
                            score = 35000 + len(card.energies) * 3500 + card.hp
                        else:
                            score = 20000 + len(card.energies) * 2500 + card.hp
                elif isinstance(card, Pokemon):
                    damage = _max_damage(active, card, roserade_count, premium_used)
                    score = _target_score(
                        card,
                        damage,
                        len(my_state.prize),
                        len(opponent.prize),
                        active,
                    )
            elif context == SelectContext.SETUP_BENCH_POKEMON:
                score = (
                    95000
                    if card.id == CYNTHIAS_GIBLE
                    else 92000 if card.id == CYNTHIAS_ROSELIA else -1
                )
                score -= option_occurrence[card.id] * 6000
            elif context == SelectContext.TO_BENCH:
                score = _to_bench_score(
                    card.id,
                    effect_id,
                    option_occurrence[card.id],
                    field_counts,
                    dragon_target,
                )
            elif context == SelectContext.TO_HAND:
                score = _search_score(
                    card,
                    effect_id,
                    field_counts,
                    hand_counts,
                    discard_counts,
                    my_state,
                    opponent,
                    stadium_id,
                )
                score -= option_occurrence[card.id] * 500
            elif context == SelectContext.DISCARD:
                score = 10000 - _hand_value(
                    card.id, field_counts, hand_counts, discard_counts
                )
            else:
                score = _search_score(
                    card,
                    effect_id,
                    field_counts,
                    hand_counts,
                    discard_counts,
                    my_state,
                    opponent,
                    stadium_id,
                )
            if card is not None:
                option_occurrence[card.id] += 1
        elif option.type in {OptionType.ENERGY_CARD, OptionType.ENERGY}:
            pokemon = get_card(obs, option.area, option.index, option.playerIndex)
            if isinstance(pokemon, Pokemon) and option.energyIndex is not None:
                energy_card = pokemon.energyCards[option.energyIndex]
                score = 100 if energy_card.id == BASIC_FIGHTING_ENERGY else 20
        elif option.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            score = (
                _play_score(
                    card,
                    obs,
                    field_counts,
                    hand_counts,
                    discard_counts,
                    unseen_counts,
                    stadium_id,
                    roserade_count,
                )
                if isinstance(card, Card)
                else -1
            )
        elif option.type == OptionType.ATTACH:
            card = get_card(obs, option.area, option.index, my_index)
            pokemon = get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
            score = (
                _attach_score(
                    card,
                    pokemon,
                    option.inPlayArea == AreaType.ACTIVE,
                    my_state,
                    opponent,
                    roserade_count,
                )
                if isinstance(card, Card) and isinstance(pokemon, Pokemon)
                else -1
            )
        elif option.type == OptionType.EVOLVE:
            score = _evolve_score(obs, option, field_counts)
        elif option.type == OptionType.ABILITY:
            card = get_card(obs, option.area, option.index, my_index)
            if card is not None and card.id == CYNTHIAS_GABITE:
                has_target = any(
                    unseen_counts[card_id] > 0 for card_id in CYNTHIAS_POKEMON
                )
                score = 132000 if has_target else 50000
            else:
                score = 50000
        elif option.type == OptionType.RETREAT:
            if active is not None and active.id in {
                CYNTHIAS_ROSELIA,
                CYNTHIAS_ROSERADE,
            }:
                if bench_ready:
                    score = 108000
                elif bench_attack_damage > 0 and (
                    not active_ready or bench_attack_damage > active_damage
                ):
                    score = 106000
                else:
                    score = -1
            else:
                score = (
                    104000
                    if bench_ready and not active_ready
                    else (
                        92000
                        if active is not None
                        and active.id != CYNTHIAS_GARCHOMP_EX
                        and bench_ready
                        else -1
                    )
                )
        elif option.type == OptionType.ATTACK:
            score = _attack_score(
                option.attackId,
                active,
                opponent_active,
                roserade_count,
                len(opponent.prize),
                bench_ready,
                energy_in_hand,
            )
        elif option.type == OptionType.END:
            score = 0
        scores.append(score)

    ordered = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    output: list[int] = []
    for index, score in ordered:
        if len(output) >= select.maxCount:
            break
        if score < 0 and len(output) >= select.minCount:
            continue
        output.append(index)
    if len(output) < select.minCount:
        selected = set(output)
        for index, _ in ordered:
            if index not in selected:
                output.append(index)
                selected.add(index)
            if len(output) >= select.minCount:
                break
    return output
