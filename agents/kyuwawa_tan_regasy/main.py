import os
from collections import Counter
from dataclasses import dataclass

from cg.api import (
    AreaType,
    Card,
    CardType,
    Observation,
    Option,
    OptionType,
    Pokemon,
    SelectContext,
    all_attack,
    all_card_data,
    to_observation_class,
)

# Card IDs in this deck.
COMFEY = 164
BUDEW = 235
BASIC_PSYCHIC_ENERGY = 5
LEGACY_ENERGY = 12

HAND_TRIMMER = 1087
ACCOMPANYING_FLUTE = 1091
NIGHT_STRETCHER = 1097
ROOT_FOSSIL = 1099
ENERGY_RETRIEVAL = 1118
ENERGY_SEARCH = 1119
POKEGEAR = 1122
POKEMON_CATCHER = 1124
COVER_FOSSIL = 1136
PLUME_FOSSIL = 1138
LANAS_AID = 1184
ERI = 1186
COLRESS_TENACITY = 1194
XEROSICS_MACHINATIONS = 1197
TEAM_ROCKETS_PETREL = 1219
CIPHERMANIACS_CODEBREAKING = 1188
GRAVITY_GEMSTONE = 1166
NEUTRALIZATION_ZONE = 1247
LIVELY_STADIUM = 1251
NIGHTTIME_MINE = 1266
MIST_ENERGY = 11

FLOWER_SHOWER = 215
PLAY_ROUGH = 216

FOSSILS = {ROOT_FOSSIL, COVER_FOSSIL, PLUME_FOSSIL}
ENERGY_CARDS = {BASIC_PSYCHIC_ENERGY, LEGACY_ENERGY}
RECOVERABLE_ENERGY_CARDS = {BASIC_PSYCHIC_ENERGY}
SUPPORTERS = {
    LANAS_AID,
    ERI,
    COLRESS_TENACITY,
    XEROSICS_MACHINATIONS,
    TEAM_ROCKETS_PETREL,
    CIPHERMANIACS_CODEBREAKING,
}
STADIUMS = {LIVELY_STADIUM, NIGHTTIME_MINE}
HAND_REDUCING_PLAY_CARDS = (
    FOSSILS
    | STADIUMS
    | {
        COMFEY,
        ACCOMPANYING_FLUTE,
        POKEMON_CATCHER,
        ERI,
        XEROSICS_MACHINATIONS,
        CIPHERMANIACS_CODEBREAKING,
    }
)
HAND_TRIMMER_DELAY_MIN_SCORE = 5000

# Rough pressure estimates for common metagame attackers.
META_DAMAGE = {
    121: 260,  # Dragapult ex
    265: 160,  # Iono's Voltorb with Voltaic Chain scaling
    245: 140,  # Alakazam
    266: 999,  # Iono's Electrode
    269: 230,  # Iono's Bellibolt ex
    345: 120,  # Crustle
    361: 140,  # Misty's Starmie after evolving
    533: 140,  # Crustle
    678: 270,  # Mega Lucario ex
    721: 180,  # Kyogre after Water Energy reaches the discard
    723: 300,  # Mega Abomasnow ex
    743: 180,  # Alakazam
    1031: 210,  # Mega Starmie ex
}
BENCH_SNIPE_ATTACKERS = {121, 1031}
EFFECT_PRESSURE_POKEMON = {BUDEW, 121, 245, 743, 1031}
EVOLUTION_BASIC_RISKS = {119, 265, 270, 360, 677, 1030}


def read_deck_csv() -> list[int]:
    file_path = "deck.csv"
    if not os.path.exists(file_path):
        file_path = "/kaggle_simulations/agent/" + file_path
    with open(file_path, "r") as file:
        rows = file.read().splitlines()
    return [int(rows[i]) for i in range(60)]


MY_DECK = read_deck_csv()
CARD_TABLE = {card.cardId: card for card in all_card_data()}
ATTACK_TABLE = {attack.attackId: attack for attack in all_attack()}
EVOLUTIONS_BY_FROM: dict[str, list] = {}
for card in CARD_TABLE.values():
    if card.evolvesFrom:
        EVOLUTIONS_BY_FROM.setdefault(card.evolvesFrom, []).append(card)


@dataclass
class BoardInfo:
    my_index: int
    op_index: int
    my_active: Pokemon | None
    op_active: Pokemon | None
    my_field: list[Pokemon]
    op_field: list[Pokemon]
    hand_counts: Counter
    discard_counts: Counter
    field_counts: Counter
    fossil_count: int
    bench_fossil_count: int
    bench_comfey_count: int
    target_fossils: int
    stadium_id: int
    active_has_gravity: bool
    active_has_basic_psychic: bool
    active_has_legacy: bool
    active_has_attack_energy: bool
    active_has_mist: bool
    rule_box_pressure: bool
    neutralization_urgent: bool
    opponent_stadium_in_play: bool
    effect_pressure: bool
    tera_pressure: bool
    fossil_wall_lock: bool
    best_trap_score: int
    active_trap_score: int


def active_pokemon(player_state) -> Pokemon | None:
    if player_state.active and player_state.active[0] is not None:
        return player_state.active[0]
    return None


def in_play_pokemon(player_state) -> list[Pokemon]:
    cards: list[Pokemon] = []
    active = active_pokemon(player_state)
    if active is not None:
        cards.append(active)
    cards.extend(player_state.bench)
    return cards


def get_card(
    obs: Observation,
    area: AreaType | None,
    index: int | None,
    player_index: int | None,
) -> Pokemon | Card | None:
    if area is None or index is None:
        return None
    state = obs.current
    if state is None:
        return None

    try:
        if area == AreaType.DECK:
            if obs.select is None or obs.select.deck is None:
                return None
            return obs.select.deck[index]
        if area == AreaType.HAND:
            hand = state.players[player_index].hand
            if hand is None:
                return None
            return hand[index]
        if area == AreaType.DISCARD:
            return state.players[player_index].discard[index]
        if area == AreaType.ACTIVE:
            return state.players[player_index].active[index]
        if area == AreaType.BENCH:
            return state.players[player_index].bench[index]
        if area == AreaType.PRIZE:
            return state.players[player_index].prize[index]
        if area == AreaType.STADIUM:
            return state.stadium[index]
        if area == AreaType.LOOKING:
            if state.looking is None:
                return None
            return state.looking[index]
    except (IndexError, TypeError):
        return None
    return None


def card_data(card_id: int):
    return CARD_TABLE.get(card_id)


def is_rule_box(pokemon: Pokemon | None) -> bool:
    if pokemon is None:
        return False
    data = card_data(pokemon.id)
    return bool(data and (data.ex or data.megaEx or data.tera))


def tool_ids(pokemon: Pokemon | None) -> set[int]:
    if pokemon is None:
        return set()
    return {tool.id for tool in pokemon.tools}


def energy_card_ids(pokemon: Pokemon | None) -> set[int]:
    if pokemon is None:
        return set()
    return {energy.id for energy in pokemon.energyCards}


def has_basic_psychic(pokemon: Pokemon | None) -> bool:
    return BASIC_PSYCHIC_ENERGY in energy_card_ids(pokemon)


def has_legacy_energy(pokemon: Pokemon | None) -> bool:
    return LEGACY_ENERGY in energy_card_ids(pokemon)


def has_attack_energy(pokemon: Pokemon | None) -> bool:
    return bool(energy_card_ids(pokemon) & ENERGY_CARDS)


def has_mist_energy(pokemon: Pokemon | None) -> bool:
    return MIST_ENERGY in energy_card_ids(pokemon)


def has_gravity(pokemon: Pokemon | None) -> bool:
    return GRAVITY_GEMSTONE in tool_ids(pokemon)


def visible_attack_damage(pokemon: Pokemon | None, extra_energy: int = 1) -> int:
    if pokemon is None:
        return 0
    if pokemon.id in META_DAMAGE:
        return META_DAMAGE[pokemon.id]

    data = card_data(pokemon.id)
    if data is None:
        return 0

    available = len(pokemon.energies) + extra_energy
    best = 0
    for attack_id in data.attacks:
        attack = ATTACK_TABLE.get(attack_id)
        if attack is None:
            continue
        if len(attack.energies) <= available:
            best = max(best, attack.damage)
    return best


def estimated_attack_damage_for_card(card_id: int, available_energy: int) -> int:
    data = card_data(card_id)
    if data is None:
        return 0

    best = 0
    for attack_id in data.attacks:
        attack = ATTACK_TABLE.get(attack_id)
        if attack is None or len(attack.energies) > available_energy:
            continue
        damage = attack.damage
        if "Knocked Out" in attack.text:
            damage = max(damage, 999)
        if card_id in META_DAMAGE:
            damage = max(damage, META_DAMAGE[card_id])
        best = max(best, damage)
    return best


def evolution_attack_damage(pokemon: Pokemon | None, extra_energy: int = 1) -> int:
    if pokemon is None:
        return 0
    data = card_data(pokemon.id)
    if data is None:
        return 0

    available_energy = len(pokemon.energies) + extra_energy
    best = 0
    for evolution in EVOLUTIONS_BY_FROM.get(data.name, []):
        best = max(
            best,
            estimated_attack_damage_for_card(evolution.cardId, available_energy),
        )
    return best


def next_turn_attack_damage(pokemon: Pokemon | None) -> int:
    return max(
        visible_attack_damage(pokemon, extra_energy=1),
        evolution_attack_damage(pokemon, extra_energy=1),
    )


def card_can_damage_bench(card_id: int) -> bool:
    if card_id in BENCH_SNIPE_ATTACKERS:
        return True
    data = card_data(card_id)
    if data is None:
        return False
    for attack_id in data.attacks:
        attack = ATTACK_TABLE.get(attack_id)
        if attack and "Bench" in attack.text:
            return True
    return False


def can_damage_bench_next_turn(pokemon: Pokemon | None) -> bool:
    if pokemon is None:
        return False
    if card_can_damage_bench(pokemon.id):
        return True
    data = card_data(pokemon.id)
    if data is None:
        return False
    return any(
        card_can_damage_bench(evolution.cardId)
        for evolution in EVOLUTIONS_BY_FROM.get(data.name, [])
    )


def can_attack_soon(pokemon: Pokemon | None) -> bool:
    if pokemon is None:
        return False
    data = card_data(pokemon.id)
    if data is None:
        return False
    available = len(pokemon.energies) + 1
    for attack_id in data.attacks:
        attack = ATTACK_TABLE.get(attack_id)
        if (
            attack
            and len(attack.energies) <= available
            and (attack.damage > 0 or "Knocked Out" in attack.text)
        ):
            return True
    return False


def trap_score(pokemon: Pokemon | None) -> int:
    if pokemon is None:
        return -100000
    data = card_data(pokemon.id)
    if data is None:
        return 0

    score = data.retreatCost * 260
    score -= len(pokemon.energies) * 180
    score -= visible_attack_damage(pokemon, extra_energy=0)

    if not can_attack_soon(pokemon):
        score += 180
    if data.stage2:
        score += 80
    elif data.stage1:
        score += 40
    if pokemon.id in BENCH_SNIPE_ATTACKERS:
        score -= 250
    if pokemon.id in EVOLUTION_BASIC_RISKS and data.retreatCost <= 1:
        score -= 220
    if is_rule_box(pokemon) and len(pokemon.energies) >= 1:
        score -= 200
    return score


def opponent_has_rule_box_pressure(op_field: list[Pokemon]) -> bool:
    return any(is_rule_box(p) and visible_attack_damage(p) >= 70 for p in op_field)


def next_turn_ex_attack_damage(pokemon: Pokemon | None) -> int:
    if pokemon is None:
        return 0
    data = card_data(pokemon.id)
    if data is None:
        return 0

    available_energy = len(pokemon.energies) + 1
    best = 0
    if data.ex or data.megaEx:
        best = max(best, estimated_attack_damage_for_card(pokemon.id, available_energy))

    for evolution in EVOLUTIONS_BY_FROM.get(data.name, []):
        if evolution.ex or evolution.megaEx:
            best = max(
                best,
                estimated_attack_damage_for_card(evolution.cardId, available_energy),
            )
    return best


def visible_non_rule_box_attack_damage(pokemon: Pokemon | None) -> int:
    if pokemon is None or is_rule_box(pokemon):
        return 0
    return visible_attack_damage(pokemon, extra_energy=1)


def neutralization_zone_is_urgent(
    my_state, op_state, op_active: Pokemon | None
) -> bool:
    my_active = active_pokemon(my_state)
    if my_active is None or op_active is None:
        return False

    if visible_non_rule_box_attack_damage(op_active) >= my_active.hp:
        return False

    incoming_ex_damage = next_turn_ex_attack_damage(op_active)
    if incoming_ex_damage < my_active.hp:
        return False

    no_backup_pokemon = len(my_state.bench) == 0
    opponent_takes_last_prize = len(op_state.prize) <= 1
    return no_backup_pokemon or opponent_takes_last_prize


def opponent_has_effect_pressure(op_field: list[Pokemon]) -> bool:
    return any(p.id in EFFECT_PRESSURE_POKEMON for p in op_field)


def opponent_has_tera_pressure(op_field: list[Pokemon]) -> bool:
    for pokemon in op_field:
        data = card_data(pokemon.id)
        if data and data.tera and visible_attack_damage(pokemon) > 0:
            return True
    return False


def fossil_wall_lock_is_available(
    op_active: Pokemon | None, op_field: list[Pokemon], active_trap_score: int
) -> bool:
    if op_active is None or active_trap_score < 700:
        return False
    if next_turn_attack_damage(op_active) > 0:
        return False
    return not any(can_damage_bench_next_turn(pokemon) for pokemon in op_field)


def max_opponent_next_turn_damage(op_field: list[Pokemon]) -> int:
    return max((next_turn_attack_damage(pokemon) for pokemon in op_field), default=0)


def opponent_can_ko_next_turn(target: Pokemon | None, info: BoardInfo) -> bool:
    if target is None:
        return False
    return max_opponent_next_turn_damage(info.op_field) >= target.hp


def estimate_target_fossils(
    my_state, op_field: list[Pokemon], my_active: Pokemon | None
) -> int:
    if my_active is None:
        return 2

    bench_snipe = any(can_damage_bench_next_turn(pokemon) for pokemon in op_field)
    max_next_damage = max(
        (next_turn_attack_damage(pokemon) for pokemon in op_field), default=0
    )
    next_attack_can_ko = max_next_damage >= my_active.hp

    target = 2
    if not bench_snipe:
        target = 3
    if next_attack_can_ko:
        target = 3 if not bench_snipe else 2
    if my_state.deckCount <= 6:
        target = max(target, 2)
    return min(target, 3)


def build_board_info(obs: Observation) -> BoardInfo:
    state = obs.current
    my_index = state.yourIndex
    op_index = 1 - my_index
    my_state = state.players[my_index]
    op_state = state.players[op_index]

    my_active = active_pokemon(my_state)
    op_active = active_pokemon(op_state)
    my_field = in_play_pokemon(my_state)
    op_field = in_play_pokemon(op_state)

    hand_counts = Counter(card.id for card in (my_state.hand or []))
    discard_counts = Counter(card.id for card in my_state.discard)
    field_counts = Counter(pokemon.id for pokemon in my_field)
    fossil_count = sum(1 for pokemon in my_field if pokemon.id in FOSSILS)
    bench_fossil_count = sum(1 for pokemon in my_state.bench if pokemon.id in FOSSILS)
    bench_comfey_count = sum(1 for pokemon in my_state.bench if pokemon.id == COMFEY)
    stadium_id = state.stadium[0].id if state.stadium else 0
    opponent_stadium_in_play = bool(
        state.stadium and state.stadium[0].playerIndex == op_index
    )

    best_bench_trap = max((trap_score(p) for p in op_state.bench), default=-100000)
    active_trap = trap_score(op_active)

    return BoardInfo(
        my_index=my_index,
        op_index=op_index,
        my_active=my_active,
        op_active=op_active,
        my_field=my_field,
        op_field=op_field,
        hand_counts=hand_counts,
        discard_counts=discard_counts,
        field_counts=field_counts,
        fossil_count=fossil_count,
        bench_fossil_count=bench_fossil_count,
        bench_comfey_count=bench_comfey_count,
        target_fossils=estimate_target_fossils(my_state, op_field, my_active),
        stadium_id=stadium_id,
        active_has_gravity=has_gravity(my_active),
        active_has_basic_psychic=has_basic_psychic(my_active),
        active_has_legacy=has_legacy_energy(my_active),
        active_has_attack_energy=has_attack_energy(my_active),
        active_has_mist=has_mist_energy(my_active),
        rule_box_pressure=opponent_has_rule_box_pressure(op_field),
        neutralization_urgent=neutralization_zone_is_urgent(
            my_state, op_state, op_active
        ),
        opponent_stadium_in_play=opponent_stadium_in_play,
        effect_pressure=opponent_has_effect_pressure(op_field),
        tera_pressure=opponent_has_tera_pressure(op_field),
        fossil_wall_lock=fossil_wall_lock_is_available(
            op_active, op_field, active_trap
        ),
        best_trap_score=best_bench_trap,
        active_trap_score=active_trap,
    )


def deck_is_safe_to_thin(
    my_deck_count: int, op_deck_count: int, amount: int = 1
) -> bool:
    if my_deck_count - amount <= 0:
        return False
    return my_deck_count - amount >= min(3, op_deck_count - 8)


def visible_energy_for_next_comfey(info: BoardInfo) -> bool:
    return bool(
        info.hand_counts[LEGACY_ENERGY]
        or info.hand_counts[BASIC_PSYCHIC_ENERGY]
        or info.hand_counts[ENERGY_SEARCH]
        or (
            info.discard_counts[BASIC_PSYCHIC_ENERGY]
            and (
                info.hand_counts[NIGHT_STRETCHER]
                or info.hand_counts[ENERGY_RETRIEVAL]
                or info.hand_counts[LANAS_AID]
            )
        )
        or info.hand_counts[COLRESS_TENACITY]
        or info.hand_counts[TEAM_ROCKETS_PETREL]
    )


def comfey_restore_prepared(info: BoardInfo, obs: Observation) -> bool:
    """次ターンにキュワワーを復帰させて技へ向かう道筋が見えているか。"""
    state = obs.current
    my_state = state.players[info.my_index]

    bench_ready = any(
        pokemon.id == COMFEY
        and (has_attack_energy(pokemon) or visible_energy_for_next_comfey(info))
        for pokemon in my_state.bench
    )
    if bench_ready:
        return True

    can_play_comfey_from_hand = bool(
        info.hand_counts[COMFEY] and len(my_state.bench) < my_state.benchMax
    )
    if can_play_comfey_from_hand and visible_energy_for_next_comfey(info):
        return True

    comfey_can_be_in_discard_next_turn = bool(
        info.discard_counts[COMFEY]
        or any(pokemon.id == COMFEY for pokemon in info.my_field)
    )
    recovery_access = bool(
        info.hand_counts[NIGHT_STRETCHER]
        or info.hand_counts[LANAS_AID]
        or info.hand_counts[TEAM_ROCKETS_PETREL]
    )

    return (
        comfey_can_be_in_discard_next_turn
        and recovery_access
        and visible_energy_for_next_comfey(info)
    )


def flower_shower_route_without_supporter(info: BoardInfo, obs: Observation) -> bool:
    if info.my_active and info.my_active.id == COMFEY and info.active_has_attack_energy:
        return True
    if comfey_from_hand_can_attack_this_turn(info, obs):
        return True
    if info.hand_counts[NIGHT_STRETCHER] and recovered_comfey_can_attack_this_turn(
        info, obs
    ):
        return True
    return benched_comfey_can_attack_after_clear(info, obs)


def xerosic_disruption_is_live(info: BoardInfo, obs: Observation) -> bool:
    state = obs.current
    op_state = state.players[info.op_index]
    return bool(
        not state.supporterPlayed
        and op_state.handCount > 0
        and comfey_restore_prepared(info, obs)
        and flower_shower_route_without_supporter(info, obs)
    )


def should_use_flower_shower(my_deck_count: int, op_deck_count: int) -> bool:
    my_after = my_deck_count - 3
    op_after = op_deck_count - 3
    if op_after <= 0 and my_deck_count >= 3:
        return True
    if my_after <= 0:
        return False
    return True


def score_flower_shower(my_deck_count: int, op_deck_count: int) -> int:
    my_after = my_deck_count - 3
    op_after = op_deck_count - 3
    if op_after <= 0 and my_deck_count >= 3:
        return 68000
    if my_after <= 0:
        return -50000

    score = 36000 + max(0, 18 - op_deck_count) * 1200
    score += (my_deck_count - op_deck_count) * 240
    if my_after <= 3:
        score -= 2200
    return score


def needs_fossil_access(info: BoardInfo) -> bool:
    return info.bench_fossil_count == 0 or info.fossil_count < info.target_fossils


def hand_trimmer_self_discard_count(my_hand_count: int) -> int:
    return max(0, my_hand_count - 6)


def option_reduces_hand_before_trimmer(
    option: Option, info: BoardInfo, obs: Observation
) -> bool:
    if option.type == OptionType.ATTACH:
        card_owner = (
            option.playerIndex if option.playerIndex is not None else info.my_index
        )
        card = get_card(obs, option.area, option.index, card_owner)
        return isinstance(card, Card)

    if option.type != OptionType.PLAY:
        return False

    card = get_card(obs, AreaType.HAND, option.index, info.my_index)
    return isinstance(card, Card) and card.id in HAND_REDUCING_PLAY_CARDS


def best_hand_reducing_setup_score_before_trimmer(
    obs: Observation, info: BoardInfo, scores: list[int], trimmer_index: int
) -> int | None:
    best_score: int | None = None
    for index, option in enumerate(obs.select.option):
        if index == trimmer_index or scores[index] < HAND_TRIMMER_DELAY_MIN_SCORE:
            continue
        if option_reduces_hand_before_trimmer(option, info, obs):
            best_score = (
                scores[index] if best_score is None else max(best_score, scores[index])
            )
    return best_score


def ciphermaniac_can_feed_flower_shower(info: BoardInfo, obs: Observation) -> bool:
    my_state = obs.current.players[info.my_index]
    return bool(
        info.my_active
        and info.my_active.id == COMFEY
        and info.active_has_attack_energy
        and my_state.deckCount > 5
        and needs_fossil_access(info)
    )


def active_fossil_can_make_room_for_comfey(info: BoardInfo) -> bool:
    return bool(info.my_active and info.my_active.id in FOSSILS)


def attack_energy_available_for_new_comfey(
    info: BoardInfo, state, include_basic_from_discard: bool = False
) -> bool:
    if state.energyAttached:
        return False
    if info.hand_counts[LEGACY_ENERGY] or info.hand_counts[BASIC_PSYCHIC_ENERGY]:
        return True
    return bool(
        include_basic_from_discard and info.discard_counts[BASIC_PSYCHIC_ENERGY]
    )


def can_bench_replacement_comfey(info: BoardInfo, my_state) -> bool:
    return (
        info.field_counts[COMFEY] == 0
        and active_fossil_can_make_room_for_comfey(info)
        and len(my_state.bench) < my_state.benchMax
    )


def comfey_from_hand_can_attack_this_turn(info: BoardInfo, obs: Observation) -> bool:
    state = obs.current
    my_state = state.players[info.my_index]
    return (
        can_bench_replacement_comfey(info, my_state)
        and info.hand_counts[COMFEY] > 0
        and attack_energy_available_for_new_comfey(info, state)
    )


def recovered_comfey_can_attack_this_turn(
    info: BoardInfo, obs: Observation, include_basic_from_discard: bool = False
) -> bool:
    state = obs.current
    my_state = state.players[info.my_index]
    return (
        can_bench_replacement_comfey(info, my_state)
        and info.discard_counts[COMFEY] > 0
        and attack_energy_available_for_new_comfey(
            info, state, include_basic_from_discard
        )
    )


def petrel_to_stretcher_can_attack_this_turn(info: BoardInfo, obs: Observation) -> bool:
    state = obs.current
    my_state = state.players[info.my_index]
    return (
        can_bench_replacement_comfey(info, my_state)
        and info.discard_counts[COMFEY] > 0
        and attack_energy_available_for_new_comfey(info, state)
    )


def benched_comfey_can_attack_after_clear(info: BoardInfo, obs: Observation) -> bool:
    if not active_fossil_can_make_room_for_comfey(info):
        return False
    my_state = obs.current.players[info.my_index]
    comfey = next((pokemon for pokemon in my_state.bench if pokemon.id == COMFEY), None)
    if comfey is None:
        return False
    if has_attack_energy(comfey):
        return True
    return attack_energy_available_for_new_comfey(info, obs.current)


def own_card_keep_value(card_id: int, info: BoardInfo, my_state) -> int:
    if card_id == COMFEY:
        return 26000 if info.field_counts[COMFEY] == 0 else 14000
    if card_id == LEGACY_ENERGY:
        if (
            info.my_active
            and info.my_active.id == COMFEY
            and not info.active_has_legacy
        ):
            return 26000
        return 12000
    if card_id == BASIC_PSYCHIC_ENERGY:
        return 18500 if not info.active_has_attack_energy else 2200
    if card_id in FOSSILS:
        if info.bench_fossil_count == 0:
            return 11500
        if info.fossil_count < info.target_fossils:
            return 9200
        return 1800
    if card_id == NIGHT_STRETCHER:
        if info.discard_counts[COMFEY] and info.field_counts[COMFEY] == 0:
            return 17000
        return 9000 if info.discard_counts[COMFEY] else 4200
    if card_id == LANAS_AID:
        if info.discard_counts[COMFEY] and info.field_counts[COMFEY] == 0:
            return 16500
        recoverable = sum(
            info.discard_counts[cid]
            for cid in FOSSILS | RECOVERABLE_ENERGY_CARDS | {COMFEY}
        )
        return 9000 if recoverable >= 2 else 3600
    if card_id == ENERGY_RETRIEVAL:
        return 7800 if info.discard_counts[BASIC_PSYCHIC_ENERGY] else 900
    if card_id == COLRESS_TENACITY:
        if not info.active_has_attack_energy or info.stadium_id not in STADIUMS:
            return 16500
        return 6200
    if card_id == TEAM_ROCKETS_PETREL:
        if info.bench_fossil_count == 0 or info.stadium_id not in STADIUMS:
            return 12500
        return 5600
    if card_id == CIPHERMANIACS_CODEBREAKING:
        if needs_fossil_access(info):
            return 16800
        return 5200
    if card_id in STADIUMS:
        if info.stadium_id != card_id:
            return 12500
        return 2500
    if card_id == POKEGEAR:
        return 7200
    if card_id == ENERGY_SEARCH:
        return 15000 if not info.active_has_attack_energy else 1800
    if card_id == POKEMON_CATCHER:
        return 5200
    if card_id == XEROSICS_MACHINATIONS:
        return 3900
    if card_id == HAND_TRIMMER:
        return 3200
    return 1000


def score_fossil_to_play(card_id: int, info: BoardInfo, obs: Observation) -> int:
    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]

    needs_bench_backup = info.bench_fossil_count == 0

    shortage = max(0, info.target_fossils - info.fossil_count)
    base = 16000 + shortage * 2800

    if needs_bench_backup:
        base += 13500
        if (
            info.my_active
            and info.my_active.id in FOSSILS
            and info.bench_comfey_count == 1
        ):
            base += 3600
    else:
        if shortage == 0:
            base = 7600

    if card_id == COVER_FOSSIL:
        return base + (1600 if info.effect_pressure else 300)
    if card_id == PLUME_FOSSIL:
        return base + (700 if info.effect_pressure else 200)
    if card_id == ROOT_FOSSIL:
        active_data = card_data(info.op_active.id) if info.op_active else None
        return base + (700 if active_data and active_data.basic else 300)
    return base


def score_play_card(card_id: int, info: BoardInfo, obs: Observation) -> int:
    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]
    op_has_energy = any(len(pokemon.energies) > 0 for pokemon in info.op_field)
    no_supporter = not state.supporterPlayed
    deck_safe = deck_is_safe_to_thin(my_state.deckCount, op_state.deckCount)
    need_energy = not info.active_has_attack_energy
    need_stadium = info.stadium_id not in STADIUMS
    need_backup = (
        info.bench_fossil_count == 0 or info.fossil_count < info.target_fossils
    )

    if card_id == COMFEY:
        if info.field_counts[COMFEY] == 0:
            return 44000 if comfey_from_hand_can_attack_this_turn(info, obs) else 28000
        return -900
    if card_id in FOSSILS:
        return score_fossil_to_play(card_id, info, obs)
    if card_id in STADIUMS:
        if info.stadium_id == card_id:
            return -700
        score = 16000 if info.stadium_id == 0 else 13200
        if card_id == NIGHTTIME_MINE and info.tera_pressure:
            score += 2600
        if card_id == LIVELY_STADIUM and info.my_active and info.my_active.id == COMFEY:
            score += 900
        return score
    if card_id == ENERGY_SEARCH:
        if need_energy and deck_safe:
            return 22000
        return -650
    if card_id == ENERGY_RETRIEVAL:
        if info.discard_counts[BASIC_PSYCHIC_ENERGY] and need_energy:
            return 14500
        if info.discard_counts[BASIC_PSYCHIC_ENERGY] >= 2 and my_state.deckCount <= 8:
            return 7200
        return -500
    if card_id == NIGHT_STRETCHER:
        if recovered_comfey_can_attack_this_turn(info, obs):
            return 43000
        if info.discard_counts[COMFEY] and info.field_counts[COMFEY] == 0:
            return 25000
        if need_energy and info.discard_counts[BASIC_PSYCHIC_ENERGY]:
            return 13200
        if info.discard_counts[COMFEY]:
            return 9200
        return -500
    if card_id == LANAS_AID and no_supporter:
        if recovered_comfey_can_attack_this_turn(
            info, obs, include_basic_from_discard=True
        ):
            return 42500
        if info.discard_counts[COMFEY] and info.field_counts[COMFEY] == 0:
            return 24500
        recoverable = sum(
            info.discard_counts[cid]
            for cid in FOSSILS | RECOVERABLE_ENERGY_CARDS | {COMFEY}
        )
        if recoverable >= 2 and (need_energy or need_backup or my_state.deckCount <= 8):
            return 14000 + recoverable * 220
        return -500
    if card_id == COLRESS_TENACITY and no_supporter:
        if deck_is_safe_to_thin(my_state.deckCount, op_state.deckCount, amount=2) and (
            need_energy or need_stadium or not info.active_has_legacy
        ):
            return 23500 if need_energy else 17500 if need_stadium else 13200
        return 5200 if deck_safe and my_state.deckCount >= 12 else -500
    if card_id == TEAM_ROCKETS_PETREL and no_supporter:
        if petrel_to_stretcher_can_attack_this_turn(info, obs):
            return 39000
        if need_backup or need_stadium or need_energy:
            return 17200
        return 7600 if deck_safe and my_state.deckCount >= 12 else -500
    if card_id == CIPHERMANIACS_CODEBREAKING and no_supporter:
        if ciphermaniac_can_feed_flower_shower(info, obs):
            return 43000
        if needs_fossil_access(info) and deck_is_safe_to_thin(
            my_state.deckCount, op_state.deckCount, amount=2
        ):
            return 24500
        if (need_energy or need_stadium) and deck_safe:
            return 12800
        return 6200 if deck_safe and my_state.deckCount >= 12 else -500
    if card_id == POKEGEAR:
        has_supporter = any(info.hand_counts[cid] for cid in SUPPORTERS)
        if (
            recovered_comfey_can_attack_this_turn(
                info, obs, include_basic_from_discard=True
            )
            and not has_supporter
        ):
            return 24000
        if deck_safe and (need_energy or need_stadium or need_backup):
            return 13200
        if deck_safe and not has_supporter:
            return 8200
        return -700
    if card_id == POKEMON_CATCHER:
        if info.best_trap_score > info.active_trap_score + 200:
            return 8500
        return 4200 if deck_safe else -600
    if card_id == XEROSICS_MACHINATIONS and no_supporter:
        if xerosic_disruption_is_live(info, obs):
            return 45500 + min(op_state.handCount, 10) * 350
        return 14000 if op_state.handCount >= 5 else 5200
    if card_id == HAND_TRIMMER:
        if op_state.handCount >= 7:
            if info.hand_counts[XEROSICS_MACHINATIONS] and xerosic_disruption_is_live(
                info, obs
            ):
                return 9800 + (op_state.handCount - 7) * 300
            return 40500 + (op_state.handCount - 7) * 700
        return 2400 if op_state.handCount >= 5 else -800
    return -1000


def score_attach_option(option: Option, info: BoardInfo, obs: Observation) -> int:
    card_owner = option.playerIndex if option.playerIndex is not None else info.my_index
    attach_card = get_card(obs, option.area, option.index, card_owner)
    target = get_card(obs, option.inPlayArea, option.inPlayIndex, info.my_index)
    if not isinstance(target, Pokemon) or not isinstance(attach_card, Card):
        return -1000

    card_id = attach_card.id
    active_target = option.inPlayArea == AreaType.ACTIVE
    target_is_comfey = target.id == COMFEY

    if not target_is_comfey:
        return -900
    if card_id == LEGACY_ENERGY:
        if has_legacy_energy(target):
            return -800
        if active_target:
            return 34000 if not has_attack_energy(target) else 30000
        return 25000 if not has_attack_energy(target) else 20000
    if card_id == BASIC_PSYCHIC_ENERGY:
        if not has_attack_energy(target):
            return 27000 if active_target else 21000
        return -500
    return -500


def score_to_active(card: Pokemon | Card | None, info: BoardInfo) -> int:
    if not isinstance(card, Pokemon):
        return -1000
    if card.id == COMFEY:
        score = 12000
        if has_attack_energy(card):
            score += 1400
        if has_legacy_energy(card):
            score += 2600
        return score
    if card.id == COVER_FOSSIL:
        return 5200 if info.effect_pressure else 4600
    if card.id == PLUME_FOSSIL:
        return 4300
    return 0


def score_switch_to_active(card: Pokemon | Card | None, info: BoardInfo) -> int:
    if (
        isinstance(card, Pokemon)
        and info.my_active
        and info.my_active.id == COMFEY
        and card.id in FOSSILS
    ):
        if info.fossil_wall_lock:
            return score_to_active(card, info) + 1800
        return -6200
    return score_to_active(card, info)


def score_flute_target(
    card: Pokemon | Card | None, info: BoardInfo, obs: Observation
) -> int:
    if card is None:
        return -1000
    data = card_data(card.id)
    if data is None or not data.basic:
        return -1000

    op_state = obs.current.players[info.op_index]
    my_state = obs.current.players[info.my_index]
    score = data.retreatCost * 240 + data.hp // 2
    if data.ex or data.megaEx:
        score -= 500
    if card.id in EVOLUTION_BASIC_RISKS:
        score -= 260
    if data.retreatCost >= 2:
        score += 280
    if op_state.deckCount <= my_state.deckCount + 3:
        score += 240
    return score


def score_petrel_to_hand(card_id: int, info: BoardInfo, obs: Observation) -> int | None:
    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]
    no_bench_fossil = info.bench_fossil_count == 0
    shortage = max(0, info.target_fossils - info.fossil_count)
    basic_energy_in_discard = info.discard_counts[BASIC_PSYCHIC_ENERGY] > 0
    deck_safe = deck_is_safe_to_thin(my_state.deckCount, op_state.deckCount)

    field_comfey_has_energy = any(
        pokemon.id == COMFEY and has_attack_energy(pokemon) for pokemon in info.my_field
    )
    has_comfey_access = bool(
        info.field_counts[COMFEY]
        or info.hand_counts[COMFEY]
        or info.discard_counts[COMFEY]
    )
    energy_access_without_petrel = bool(
        field_comfey_has_energy
        or info.hand_counts[LEGACY_ENERGY]
        or info.hand_counts[BASIC_PSYCHIC_ENERGY]
        or info.hand_counts[ENERGY_SEARCH]
        or info.hand_counts[COLRESS_TENACITY]
        or (
            basic_energy_in_discard
            and (
                info.hand_counts[NIGHT_STRETCHER]
                or info.hand_counts[ENERGY_RETRIEVAL]
                or info.hand_counts[LANAS_AID]
            )
        )
    )
    needs_energy = has_comfey_access and not energy_access_without_petrel

    has_recovery_access = bool(
        info.hand_counts[NIGHT_STRETCHER] or info.hand_counts[LANAS_AID]
    )
    has_recovery_target = bool(
        info.discard_counts[COMFEY]
        or info.field_counts[COMFEY]
        or info.hand_counts[COMFEY]
    )
    needs_recovery = has_recovery_target and not has_recovery_access

    if card_id in FOSSILS:
        if no_bench_fossil:
            score = 52000 + shortage * 2600
            if card_id == COVER_FOSSIL and info.effect_pressure:
                score += 1800
            if card_id == ROOT_FOSSIL:
                active_data = card_data(info.op_active.id) if info.op_active else None
                if active_data and active_data.basic:
                    score += 700
            return score

        if shortage <= 0:
            return -700
        score = 9200 + shortage * 1300
        if card_id == COVER_FOSSIL and info.effect_pressure:
            score += 900
        if card_id == ROOT_FOSSIL:
            active_data = card_data(info.op_active.id) if info.op_active else None
            if active_data and active_data.basic:
                score += 500
        return score

    if no_bench_fossil:
        if card_id == CIPHERMANIACS_CODEBREAKING:
            return 7000
        if card_id in {TEAM_ROCKETS_PETREL, POKEGEAR}:
            return 6200
        return None

    if not has_comfey_access and card_id == COMFEY:
        return 48000

    if needs_energy:
        if card_id == NIGHT_STRETCHER and basic_energy_in_discard:
            score = 47000
            if info.discard_counts[COMFEY]:
                score += 1400
            return score
        if card_id == ENERGY_RETRIEVAL and basic_energy_in_discard:
            return 44500
        if card_id == ENERGY_SEARCH:
            return 46500 if deck_safe else 26000
        if card_id == BASIC_PSYCHIC_ENERGY:
            return 44500
        if card_id == LEGACY_ENERGY:
            return 43000
        if card_id == COLRESS_TENACITY:
            return 32500

    if needs_recovery:
        if card_id == NIGHT_STRETCHER:
            score = 43000
            if basic_energy_in_discard:
                score += 1800
            if info.discard_counts[COMFEY]:
                score += 1400
            return score
        if card_id == LANAS_AID:
            score = 39800 if not state.supporterPlayed else 36500
            recoverable = sum(
                info.discard_counts[cid]
                for cid in FOSSILS | RECOVERABLE_ENERGY_CARDS | {COMFEY}
            )
            return score + min(recoverable, 3) * 600

    return None


def score_to_hand(
    card: Pokemon | Card | None, info: BoardInfo, obs: Observation
) -> int:
    if card is None:
        return -1000

    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]
    card_id = card.id

    effect_id = obs.select.effect.id if obs.select and obs.select.effect else 0
    if effect_id == TEAM_ROCKETS_PETREL:
        petrel_score = score_petrel_to_hand(card_id, info, obs)
        if petrel_score is not None:
            return petrel_score

    if card_id == COMFEY:
        if info.field_counts[COMFEY] == 0:
            return 44000 if recovered_comfey_can_attack_this_turn(info, obs) else 30000
        return 12000
    if card_id == LEGACY_ENERGY:
        return 30000 if not info.active_has_legacy else 9000
    if card_id == BASIC_PSYCHIC_ENERGY:
        return 22000 if not info.active_has_attack_energy else 5400
    if card_id in STADIUMS:
        score = 15200 if info.stadium_id != card_id else 2500
        if card_id == NIGHTTIME_MINE and info.tera_pressure:
            score += 2400
        if card_id == LIVELY_STADIUM and info.stadium_id not in STADIUMS:
            score += 900
        return score
    if card_id in FOSSILS:
        if info.bench_fossil_count == 0:
            return 14000
        return 10800 if info.fossil_count < info.target_fossils else 2600
    if card_id == COLRESS_TENACITY:
        if not info.active_has_attack_energy or info.stadium_id not in STADIUMS:
            return 16500
        return 6200
    if card_id == TEAM_ROCKETS_PETREL:
        if info.bench_fossil_count == 0 or info.stadium_id not in STADIUMS:
            return 13200
        return 5800
    if card_id == CIPHERMANIACS_CODEBREAKING:
        if needs_fossil_access(info):
            return 19000
        return 6200
    if card_id == LANAS_AID:
        if not comfey_restore_prepared(info, obs) and (
            info.discard_counts[COMFEY]
            or info.field_counts[COMFEY]
            or info.hand_counts[COMFEY]
        ):
            return 27000
        return 8500 if info.discard_counts[COMFEY] else 6200
    if card_id == NIGHT_STRETCHER:
        if not comfey_restore_prepared(info, obs) and (
            info.discard_counts[COMFEY] or info.field_counts[COMFEY]
        ):
            return 28500
        return 7600 if info.discard_counts[COMFEY] else 5200
    if card_id == ENERGY_RETRIEVAL:
        return 8500 if info.discard_counts[BASIC_PSYCHIC_ENERGY] else 1200
    if card_id == ENERGY_SEARCH:
        if not info.active_has_attack_energy and deck_is_safe_to_thin(
            my_state.deckCount, op_state.deckCount
        ):
            return 17000
        return 2400
    if card_id == POKEGEAR:
        return 8400
    if card_id == POKEMON_CATCHER:
        return 5600 if info.best_trap_score > info.active_trap_score + 200 else 2200
    if card_id == XEROSICS_MACHINATIONS:
        if xerosic_disruption_is_live(info, obs):
            return 30000 + min(op_state.handCount, 10) * 350
        return 10800 if op_state.handCount >= 5 else 3800
    if card_id == HAND_TRIMMER:
        if op_state.handCount >= 7:
            if info.hand_counts[XEROSICS_MACHINATIONS] and xerosic_disruption_is_live(
                info, obs
            ):
                return 6800
            return 24000 + (op_state.handCount - 7) * 500
        return 5000 if op_state.handCount >= 5 else 1200
    return own_card_keep_value(card_id, info, my_state)


def score_discard_card(
    card: Pokemon | Card | None, option: Option, info: BoardInfo, obs: Observation
) -> int:
    if card is None:
        return -1000

    state = obs.current
    my_state = state.players[info.my_index]
    card_id = card.id

    if option.playerIndex == info.op_index:
        data = card_data(card_id)
        score = 1000
        if data and data.cardType == CardType.ITEM:
            score += 4300
        if card_id in {1123, 1126, 1102, 1121, 1086, 1118, 1120, 1124}:
            score += 1600
        if card_id in ENERGY_CARDS:
            score += 900
        if data and data.cardType == CardType.SUPPORTER:
            score += 700
        return score

    keep = own_card_keep_value(card_id, info, my_state)
    duplicates = max(0, info.hand_counts[card_id] - 1)
    score = 10000 - keep + duplicates * 1000
    if card_id == LEGACY_ENERGY:
        score -= 30000
    if card_id == BASIC_PSYCHIC_ENERGY and info.hand_counts[LEGACY_ENERGY]:
        score += 500
    if card_id == COMFEY:
        score -= 30000
    return score


def score_energy_discard(option: Option, info: BoardInfo, obs: Observation) -> int:
    pokemon = get_card(obs, option.area, option.index, option.playerIndex)
    if not isinstance(pokemon, Pokemon):
        return 0

    if option.playerIndex == info.op_index:
        score = 5000 + len(pokemon.energies) * 400
        if option.area == AreaType.ACTIVE:
            score += 1800
        score += visible_attack_damage(pokemon, extra_energy=0)
        score += max(0, trap_score(pokemon)) // 2
        return score

    if pokemon.id == COMFEY:
        if has_legacy_energy(pokemon):
            return -6000
        if has_attack_energy(pokemon):
            return -3500
    return 1000


def score_clear_active_fossil(info: BoardInfo, obs: Observation) -> int:
    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]

    if not info.my_active or info.my_active.id not in FOSSILS:
        return -900

    comfey = next((pokemon for pokemon in my_state.bench if pokemon.id == COMFEY), None)
    if comfey is None:
        return -1200

    has_benched_fossil_after_clear = info.bench_fossil_count > 0
    can_rebuild_backup = has_benched_fossil_after_clear or any(
        info.hand_counts[card_id] for card_id in FOSSILS
    )
    can_win_by_flower = op_state.deckCount <= 3 and has_attack_energy(comfey)
    comfey_will_be_ko = opponent_can_ko_next_turn(comfey, info)

    if benched_comfey_can_attack_after_clear(info, obs):
        score = 45000 + (2500 if has_attack_energy(comfey) else 0)
        if can_win_by_flower:
            score += 18000
        elif not has_benched_fossil_after_clear:
            if comfey_will_be_ko:
                return -22000
            score -= 9000
        if len(op_state.prize) <= 1 and not can_win_by_flower:
            score -= 6000
        return score

    # Do not clear the fossil wall unless it immediately enables Comfey to attack.
    if has_benched_fossil_after_clear:
        score = -5200
    elif can_rebuild_backup:
        score = -7200
    else:
        score = -12000

    if can_win_by_flower:
        score += 14000

    if not has_benched_fossil_after_clear:
        if comfey_will_be_ko:
            score -= 5200
        if len(op_state.prize) <= 1:
            score -= 5200
        elif len(op_state.prize) <= 2:
            score -= 2200
        if any(can_damage_bench_next_turn(pokemon) for pokemon in info.op_field):
            score -= 1200

    if info.fossil_wall_lock:
        score -= 2400
    return score


def score_attach_target(target: Pokemon, info: BoardInfo) -> int:
    if target.id == COMFEY:
        score = 5200
        if not has_attack_energy(target):
            score += 6000
        if not has_legacy_energy(target):
            score += 4200
        return score
    if target.id in FOSSILS:
        return 400
    return 0


def ciphermaniac_future_counts(
    info: BoardInfo, stacked_counts: Counter | None = None
) -> Counter:
    counts = Counter(info.hand_counts)
    if stacked_counts:
        counts.update(stacked_counts)
    return counts


def ciphermaniac_future_energy_access(info: BoardInfo, counts: Counter) -> bool:
    field_comfey_has_energy = any(
        pokemon.id == COMFEY and has_attack_energy(pokemon) for pokemon in info.my_field
    )
    return bool(
        field_comfey_has_energy
        or counts[LEGACY_ENERGY]
        or counts[BASIC_PSYCHIC_ENERGY]
        or counts[ENERGY_SEARCH]
        or counts[COLRESS_TENACITY]
        or (
            info.discard_counts[BASIC_PSYCHIC_ENERGY]
            and (
                counts[NIGHT_STRETCHER] or counts[ENERGY_RETRIEVAL] or counts[LANAS_AID]
            )
        )
    )


def ciphermaniac_future_has_bench_fossil(
    info: BoardInfo, obs: Observation, counts: Counter
) -> bool:
    my_state = obs.current.players[info.my_index]
    return bool(
        len(my_state.bench) < my_state.benchMax
        and any(counts[card_id] for card_id in FOSSILS)
    )


def ciphermaniac_future_comfey_attack_route(
    info: BoardInfo, obs: Observation, counts: Counter, reserve_fossil_slot: bool
) -> bool:
    my_state = obs.current.players[info.my_index]
    if not ciphermaniac_future_energy_access(info, counts):
        return False

    reserved_slots = 1 if reserve_fossil_slot else 0
    free_slots = my_state.benchMax - len(my_state.bench) - reserved_slots

    if (
        info.my_active
        and info.my_active.id == COMFEY
        and not opponent_can_ko_next_turn(info.my_active, info)
    ):
        return True

    if any(pokemon.id == COMFEY for pokemon in my_state.bench):
        return True

    if counts[COMFEY] and free_slots >= 1:
        return True

    recovery_access = counts[NIGHT_STRETCHER] or counts[LANAS_AID]
    recoverable_comfey = bool(
        info.discard_counts[COMFEY]
        or any(pokemon.id == COMFEY for pokemon in info.my_field)
    )
    return bool(recovery_access and recoverable_comfey and free_slots >= 1)


def ciphermaniac_next_turn_can_bench_fossil_and_attack(
    info: BoardInfo, obs: Observation, counts: Counter
) -> bool:
    return bool(
        ciphermaniac_future_has_bench_fossil(info, obs, counts)
        and ciphermaniac_future_comfey_attack_route(
            info, obs, counts, reserve_fossil_slot=True
        )
    )


def score_ciphermaniac_stack_card(
    card: Pokemon | Card | None,
    info: BoardInfo,
    obs: Observation,
    stacked_counts: Counter | None = None,
) -> int:
    if card is None:
        return -1000

    op_state = obs.current.players[info.op_index]
    card_id = card.id
    current_counts = ciphermaniac_future_counts(info, stacked_counts)
    candidate_counts = Counter(current_counts)
    candidate_counts[card_id] += 1
    ready_before = ciphermaniac_next_turn_can_bench_fossil_and_attack(
        info, obs, current_counts
    )
    ready_after = ciphermaniac_next_turn_can_bench_fossil_and_attack(
        info, obs, candidate_counts
    )

    if ready_before:
        if card_id == XEROSICS_MACHINATIONS and op_state.handCount > 0:
            return 47000 + min(op_state.handCount, 10) * 400
        if card_id == HAND_TRIMMER:
            if op_state.handCount >= 7:
                return 45500 + (op_state.handCount - 7) * 700
            return 26000 if op_state.handCount >= 5 else 9000
        if card_id == POKEMON_CATCHER:
            return (
                32000 if info.best_trap_score > info.active_trap_score + 200 else 19000
            )
        if card_id in STADIUMS:
            score = 23000 if info.stadium_id != card_id else 4500
            if card_id == NIGHTTIME_MINE and info.tera_pressure:
                score += 2600
            return score
        if card_id == CIPHERMANIACS_CODEBREAKING:
            return 21000
        if card_id == TEAM_ROCKETS_PETREL:
            return 18500
        if card_id == POKEGEAR:
            return 16000
        if card_id in {NIGHT_STRETCHER, LANAS_AID}:
            return 11500
        if card_id in FOSSILS and info.fossil_count < info.target_fossils:
            return 9500
        return score_to_hand(card, info, obs)

    if ready_after:
        score = 52000
        if card_id in FOSSILS:
            score += 2200
        if card_id in {NIGHT_STRETCHER, LANAS_AID, COMFEY}:
            score += 1800
        if card_id in {LEGACY_ENERGY, BASIC_PSYCHIC_ENERGY, ENERGY_SEARCH}:
            score += 1400
        return score

    has_future_fossil = ciphermaniac_future_has_bench_fossil(info, obs, current_counts)
    has_future_attack = ciphermaniac_future_comfey_attack_route(
        info, obs, current_counts, reserve_fossil_slot=True
    )
    has_future_energy = ciphermaniac_future_energy_access(info, current_counts)
    has_comfey_to_restore = bool(
        info.discard_counts[COMFEY] or info.field_counts[COMFEY]
    )

    if not has_future_fossil and card_id in FOSSILS:
        score = 50000
        if card_id == COVER_FOSSIL and info.effect_pressure:
            score += 1800
        return score

    if not has_future_attack:
        if has_comfey_to_restore and card_id == NIGHT_STRETCHER:
            return 50000
        if has_comfey_to_restore and card_id == LANAS_AID:
            return 48000
        if card_id == COMFEY:
            return 47000
        if not has_future_energy:
            if card_id == LEGACY_ENERGY:
                return 43000
            if card_id == BASIC_PSYCHIC_ENERGY:
                return 40000 if not info.active_has_attack_energy else 26000
            if card_id == ENERGY_SEARCH:
                return 37000
            if (
                card_id == ENERGY_RETRIEVAL
                and info.discard_counts[BASIC_PSYCHIC_ENERGY]
            ):
                return 33000
            if card_id == COLRESS_TENACITY:
                return 32000 if not info.active_has_attack_energy else 18000
        if card_id == TEAM_ROCKETS_PETREL:
            return 30000

    future_fossil_count = info.fossil_count + sum(
        current_counts[card_id] for card_id in FOSSILS
    )
    if card_id in FOSSILS and future_fossil_count < info.target_fossils:
        return 24000
    if card_id == CIPHERMANIACS_CODEBREAKING:
        return 21000
    return score_to_hand(card, info, obs)


def score_card_option(option: Option, info: BoardInfo, obs: Observation) -> int:
    context = obs.select.context
    card = get_card(obs, option.area, option.index, option.playerIndex)

    if context in {SelectContext.SETUP_ACTIVE_POKEMON, SelectContext.TO_ACTIVE}:
        return score_to_active(card, info)

    if context == SelectContext.SWITCH:
        if option.playerIndex == info.op_index:
            return trap_score(card if isinstance(card, Pokemon) else None)
        return score_switch_to_active(card, info)

    if context in {
        SelectContext.SETUP_BENCH_POKEMON,
        SelectContext.TO_BENCH,
        SelectContext.TO_FIELD,
    }:
        if option.playerIndex == info.op_index:
            return score_flute_target(card, info, obs)
        if (
            isinstance(card, Pokemon)
            and card.id == COMFEY
            and info.field_counts[COMFEY] == 0
        ):
            return 46000 if comfey_from_hand_can_attack_this_turn(info, obs) else 28000
        if card is not None and card.id in FOSSILS:
            return score_fossil_to_play(card.id, info, obs)
        return -200

    if context == SelectContext.TO_HAND:
        return score_to_hand(card, info, obs)

    if context in {
        SelectContext.DISCARD,
        SelectContext.DISCARD_CARD_OR_ATTACHED_CARD,
        SelectContext.NOT_MOVE,
    }:
        if (
            isinstance(card, Pokemon)
            and card.id in FOSSILS
            and info.my_active
            and info.my_active.serial == card.serial
        ):
            return score_clear_active_fossil(info, obs)
        return score_discard_card(card, option, info, obs)

    if context in {SelectContext.TO_DECK, SelectContext.TO_DECK_BOTTOM}:
        if obs.select.effect and obs.select.effect.id == CIPHERMANIACS_CODEBREAKING:
            return score_ciphermaniac_stack_card(card, info, obs)
        return (
            -own_card_keep_value(card.id, info, obs.current.players[info.my_index])
            if card
            else 0
        )

    if context in {
        SelectContext.DAMAGE,
        SelectContext.DAMAGE_COUNTER,
        SelectContext.DAMAGE_COUNTER_ANY,
    }:
        if option.playerIndex == info.op_index and isinstance(card, Pokemon):
            return 5000 - card.hp
        if option.playerIndex == info.my_index and isinstance(card, Pokemon):
            return -5000 - card.hp

    if context in {SelectContext.HEAL, SelectContext.REMOVE_DAMAGE_COUNTER}:
        if option.playerIndex == info.my_index and isinstance(card, Pokemon):
            return card.maxHp - card.hp
        return -1000

    if context in {SelectContext.ATTACH_TO, SelectContext.ATTACH_FROM}:
        if isinstance(card, Pokemon):
            return score_attach_target(card, info)

    return score_to_hand(card, info, obs)


def score_number(option: Option, info: BoardInfo, obs: Observation) -> int:
    number = option.number or 0
    context = obs.select.context
    my_deck_count = obs.current.players[info.my_index].deckCount

    if context == SelectContext.DRAW_COUNT:
        if my_deck_count <= number + 3:
            return -number * 900
        if my_deck_count <= 9:
            return -number * 250
        return number * 180
    if context in {
        SelectContext.DAMAGE_COUNTER_COUNT,
        SelectContext.REMOVE_DAMAGE_COUNTER_COUNT,
    }:
        return number * 100
    return number


def score_yes_no(option: Option, info: BoardInfo, obs: Observation) -> int:
    context = obs.select.context
    yes = option.type == OptionType.YES

    if context == SelectContext.IS_FIRST:
        return -1000 if yes else 1000
    if context == SelectContext.MULLIGAN:
        return 1000 if yes else -1000
    if context == SelectContext.COIN_HEAD:
        return 1000 if yes else -1000
    if context == SelectContext.ACTIVATE:
        effect_id = obs.select.effect.id if obs.select.effect else 0
        if effect_id in {POKEGEAR, ACCOMPANYING_FLUTE}:
            return 500 if yes else -50
        return 700 if yes else -100
    return 100 if yes else 0


def score_attack(option: Option, info: BoardInfo, obs: Observation) -> int:
    my_state = obs.current.players[info.my_index]
    op_state = obs.current.players[info.op_index]
    if option.attackId == FLOWER_SHOWER:
        score = score_flower_shower(my_state.deckCount, op_state.deckCount)
        if (
            info.my_active
            and info.my_active.id == COMFEY
            and not my_state.bench
            and op_state.deckCount > 3
            and opponent_can_ko_next_turn(info.my_active, info)
        ):
            return -22000
        if info.active_has_legacy:
            score += 1800
        if info.stadium_id in STADIUMS:
            score += 800
        return score
    if option.attackId == PLAY_ROUGH:
        if info.op_active and info.op_active.id == BUDEW and info.op_active.hp <= 40:
            return 52000
        if info.op_active and info.op_active.hp <= 20:
            return 12000
        return -2500
    return -1000


def score_option(index: int, option: Option, info: BoardInfo, obs: Observation) -> int:
    if option.type == OptionType.NUMBER:
        return score_number(option, info, obs)
    if option.type in {OptionType.YES, OptionType.NO}:
        return score_yes_no(option, info, obs)
    if option.type == OptionType.CARD:
        return score_card_option(option, info, obs)
    if option.type == OptionType.TOOL_CARD:
        card = get_card(obs, option.area, option.index, option.playerIndex)
        return score_discard_card(card, option, info, obs)
    if option.type in {OptionType.ENERGY_CARD, OptionType.ENERGY}:
        return score_energy_discard(option, info, obs)
    if option.type == OptionType.PLAY:
        card = get_card(obs, AreaType.HAND, option.index, info.my_index)
        return score_play_card(card.id, info, obs) if isinstance(card, Card) else -1000
    if option.type == OptionType.ATTACH:
        return score_attach_option(option, info, obs)
    if option.type == OptionType.ABILITY:
        card = get_card(obs, option.area, option.index, info.my_index)
        if card is None:
            return -1000
        if card.id in FOSSILS:
            if info.my_active and info.my_active.serial == card.serial:
                return score_clear_active_fossil(info, obs)
            if (
                info.fossil_count > info.target_fossils + 1
                and info.bench_fossil_count > 2
            ):
                return -300
            return -1200
        if card.id == LIVELY_STADIUM:
            return 400
        return -500
    if option.type == OptionType.DISCARD:
        card = get_card(obs, option.area, option.index, info.my_index)
        if isinstance(card, Pokemon) and card.id in FOSSILS:
            if info.my_active and info.my_active.serial == card.serial:
                return score_clear_active_fossil(info, obs)
            if (
                info.fossil_count > info.target_fossils + 1
                and info.bench_fossil_count > 2
            ):
                return -200
        return -1200
    if option.type == OptionType.RETREAT:
        if (
            info.my_active
            and info.my_active.id in FOSSILS
            and info.bench_comfey_count >= 1
        ):
            return score_clear_active_fossil(info, obs) - 500
        return -900
    if option.type == OptionType.ATTACK:
        return score_attack(option, info, obs)
    if option.type == OptionType.END:
        my_state = obs.current.players[info.my_index]
        op_state = obs.current.players[info.op_index]
        score = 300
        if not should_use_flower_shower(my_state.deckCount, op_state.deckCount):
            score += 1200
        return score
    if option.type == OptionType.SKILL:
        return 100
    if option.type == OptionType.SPECIAL_CONDITION:
        return 0
    return 0


def flower_shower_is_available(
    obs: Observation, scores: list[int] | None = None
) -> bool:
    for index, option in enumerate(obs.select.option):
        if option.type == OptionType.ATTACK and option.attackId == FLOWER_SHOWER:
            return scores is None or scores[index] > 0
    return False


def has_pending_setup_before_terminal_action(
    obs: Observation, info: BoardInfo, scores: list[int]
) -> bool:
    select = obs.select
    if select.context != SelectContext.MAIN:
        return False

    flower_ready = flower_shower_is_available(obs, scores)
    bench_fossil_critical = info.bench_fossil_count == 0
    op_state = obs.current.players[info.op_index]

    for index, option in enumerate(select.option):
        if option.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, option.index, info.my_index)
            if not isinstance(card, Card) or scores[index] <= 0:
                continue

            if bench_fossil_critical and card.id in FOSSILS:
                return True

            if flower_ready:
                if card.id in FOSSILS and info.bench_fossil_count == 0:
                    return True
                if (
                    card.id == CIPHERMANIACS_CODEBREAKING
                    and ciphermaniac_can_feed_flower_shower(info, obs)
                ):
                    return True
                if card.id == XEROSICS_MACHINATIONS and xerosic_disruption_is_live(
                    info, obs
                ):
                    return True
                if card.id == HAND_TRIMMER and op_state.handCount >= 7:
                    return True
                continue

            if card.id == COMFEY and comfey_from_hand_can_attack_this_turn(info, obs):
                return True
            if card.id == NIGHT_STRETCHER and recovered_comfey_can_attack_this_turn(
                info, obs
            ):
                return True
            if card.id == LANAS_AID and recovered_comfey_can_attack_this_turn(
                info, obs, include_basic_from_discard=True
            ):
                return True
            if (
                card.id == TEAM_ROCKETS_PETREL
                and petrel_to_stretcher_can_attack_this_turn(info, obs)
            ):
                return True

            if card.id in FOSSILS and (
                info.fossil_count < info.target_fossils or info.bench_fossil_count == 0
            ):
                return True
            if card.id == XEROSICS_MACHINATIONS and xerosic_disruption_is_live(
                info, obs
            ):
                return True
            if card.id == HAND_TRIMMER and op_state.handCount >= 7:
                return True
            if card.id in STADIUMS:
                return True
            if card.id in {
                ENERGY_SEARCH,
                COLRESS_TENACITY,
                TEAM_ROCKETS_PETREL,
                CIPHERMANIACS_CODEBREAKING,
                POKEGEAR,
            }:
                if (
                    not info.active_has_attack_energy
                    or not info.active_has_legacy
                    or info.stadium_id not in STADIUMS
                    or info.bench_fossil_count == 0
                ):
                    return True
        elif option.type == OptionType.ATTACH:
            card_owner = (
                option.playerIndex if option.playerIndex is not None else info.my_index
            )
            card = get_card(obs, option.area, option.index, card_owner)
            if isinstance(card, Card) and card.id in ENERGY_CARDS and scores[index] > 0:
                return True
    return False


def terminal_action_can_win_now(
    obs: Observation, option: Option, info: BoardInfo
) -> bool:
    if option.type != OptionType.ATTACK or option.attackId != FLOWER_SHOWER:
        return False
    op_state = obs.current.players[info.op_index]
    return op_state.deckCount <= 3


def order_scores_for_execution(
    obs: Observation, info: BoardInfo, scores: list[int]
) -> list[int]:
    adjusted = list(scores)

    bench_fossil_critical = info.bench_fossil_count == 0
    my_state = obs.current.players[info.my_index]
    hand_trimmer_self_discards = hand_trimmer_self_discard_count(my_state.handCount)

    for index, option in enumerate(obs.select.option):
        if option.type == OptionType.PLAY and bench_fossil_critical:
            card = get_card(obs, AreaType.HAND, option.index, info.my_index)
            if isinstance(card, Card) and card.id in FOSSILS:
                adjusted[index] = max(adjusted[index], 36000)

    if hand_trimmer_self_discards > 0:
        for index, option in enumerate(obs.select.option):
            if option.type != OptionType.PLAY:
                continue
            card = get_card(obs, AreaType.HAND, option.index, info.my_index)
            if not isinstance(card, Card) or card.id != HAND_TRIMMER:
                continue
            setup_score = best_hand_reducing_setup_score_before_trimmer(
                obs, info, adjusted, index
            )
            if setup_score is not None:
                adjusted[index] = min(adjusted[index], setup_score - 800)

    if not has_pending_setup_before_terminal_action(obs, info, scores):
        return adjusted

    for index, option in enumerate(obs.select.option):
        if option.type == OptionType.END:
            adjusted[index] = min(adjusted[index], -2000)
        elif option.type == OptionType.ATTACK and not terminal_action_can_win_now(
            obs, option, info
        ):
            adjusted[index] = min(adjusted[index], -2000)
    return adjusted


def choose_by_scores(obs: Observation, scores: list[int]) -> list[int]:
    select = obs.select
    if select.maxCount == 0 or not select.option:
        return []

    ranked = sorted(range(len(scores)), key=lambda i: (scores[i], -i), reverse=True)
    chosen: list[int] = []

    for option_index in ranked:
        if len(chosen) >= select.maxCount:
            break
        if len(chosen) < select.minCount or scores[option_index] > 0:
            chosen.append(option_index)

    if len(chosen) < select.minCount:
        for option_index in ranked:
            if option_index not in chosen:
                chosen.append(option_index)
                if len(chosen) >= select.minCount:
                    break
    return chosen[: select.maxCount]


def choose_ciphermaniac_stack_options(
    obs: Observation, info: BoardInfo
) -> list[int] | None:
    select = obs.select
    if (
        select is None
        or select.context not in {SelectContext.TO_DECK, SelectContext.TO_DECK_BOTTOM}
        or select.effect is None
        or select.effect.id != CIPHERMANIACS_CODEBREAKING
    ):
        return None

    chosen: list[int] = []
    stacked_counts: Counter = Counter()
    remaining = set(range(len(select.option)))

    while remaining and len(chosen) < select.maxCount:
        best_index: int | None = None
        best_score: int | None = None
        for index in remaining:
            card = get_card(
                obs,
                select.option[index].area,
                select.option[index].index,
                select.option[index].playerIndex,
            )
            score = score_ciphermaniac_stack_card(card, info, obs, stacked_counts)
            if (
                best_score is None
                or best_index is None
                or (score, -index) > (best_score, -best_index)
            ):
                best_index = index
                best_score = score

        if best_index is None or best_score is None:
            break
        if len(chosen) >= select.minCount and best_score <= 0:
            break

        chosen.append(best_index)
        remaining.remove(best_index)
        card = get_card(
            obs,
            select.option[best_index].area,
            select.option[best_index].index,
            select.option[best_index].playerIndex,
        )
        if card is not None:
            stacked_counts[card.id] += 1

    if len(chosen) < select.minCount:
        fallback_scores = [
            score_ciphermaniac_stack_card(
                get_card(obs, option.area, option.index, option.playerIndex),
                info,
                obs,
                stacked_counts,
            )
            for option in select.option
        ]
        for option_index in sorted(
            range(len(fallback_scores)),
            key=lambda i: (fallback_scores[i], -i),
            reverse=True,
        ):
            if option_index in chosen:
                continue
            chosen.append(option_index)
            if len(chosen) >= select.minCount:
                break

    return chosen[: select.maxCount]


def play_card_id_for_option(
    obs: Observation, info: BoardInfo, option: Option
) -> int | None:
    if option.type != OptionType.PLAY:
        return None
    card = get_card(obs, AreaType.HAND, option.index, info.my_index)
    return card.id if isinstance(card, Card) else None


def choose_play_option_for_ids(
    obs: Observation, info: BoardInfo, card_ids: list[int]
) -> int | None:
    for card_id in card_ids:
        for index, option in enumerate(obs.select.option):
            if play_card_id_for_option(obs, info, option) == card_id:
                return index
    return None


def choose_fossil_play_option(obs: Observation, info: BoardInfo) -> int | None:
    active_data = card_data(info.op_active.id) if info.op_active else None
    if info.effect_pressure:
        preference = [COVER_FOSSIL, PLUME_FOSSIL, ROOT_FOSSIL]
    elif active_data and active_data.basic:
        preference = [ROOT_FOSSIL, COVER_FOSSIL, PLUME_FOSSIL]
    else:
        preference = [COVER_FOSSIL, ROOT_FOSSIL, PLUME_FOSSIL]
    return choose_play_option_for_ids(obs, info, preference)


def choose_stadium_play_option(obs: Observation, info: BoardInfo) -> int | None:
    if info.tera_pressure:
        preference = [NIGHTTIME_MINE, LIVELY_STADIUM]
    elif info.my_active and info.my_active.id == COMFEY:
        preference = [LIVELY_STADIUM, NIGHTTIME_MINE]
    elif info.opponent_stadium_in_play:
        preference = [NIGHTTIME_MINE, LIVELY_STADIUM]
    else:
        preference = [LIVELY_STADIUM, NIGHTTIME_MINE]

    for card_id in preference:
        if info.stadium_id == card_id:
            continue
        option_index = choose_play_option_for_ids(obs, info, [card_id])
        if option_index is not None:
            return option_index
    return None


def choose_attack_energy_attach_option(obs: Observation, info: BoardInfo) -> int | None:
    preferences = [
        (
            LEGACY_ENERGY,
            lambda target, active: active
            and target.id == COMFEY
            and not has_attack_energy(target),
        ),
        (
            BASIC_PSYCHIC_ENERGY,
            lambda target, active: active
            and target.id == COMFEY
            and not has_attack_energy(target),
        ),
        (
            LEGACY_ENERGY,
            lambda target, active: active
            and target.id == COMFEY
            and not has_legacy_energy(target),
        ),
        (
            LEGACY_ENERGY,
            lambda target, active: (not active)
            and target.id == COMFEY
            and not has_attack_energy(target),
        ),
        (
            BASIC_PSYCHIC_ENERGY,
            lambda target, active: (not active)
            and target.id == COMFEY
            and not has_attack_energy(target),
        ),
    ]

    for card_id, target_predicate in preferences:
        for index, option in enumerate(obs.select.option):
            if option.type != OptionType.ATTACH:
                continue
            card_owner = (
                option.playerIndex if option.playerIndex is not None else info.my_index
            )
            attach_card = get_card(obs, option.area, option.index, card_owner)
            target = get_card(obs, option.inPlayArea, option.inPlayIndex, info.my_index)
            active_target = option.inPlayArea == AreaType.ACTIVE
            if (
                isinstance(attach_card, Card)
                and attach_card.id == card_id
                and isinstance(target, Pokemon)
                and target_predicate(target, active_target)
            ):
                return index
    return None


def choose_clear_active_fossil_option(obs: Observation, info: BoardInfo) -> int | None:
    if info.bench_fossil_count == 0 or not benched_comfey_can_attack_after_clear(
        info, obs
    ):
        return None

    for option_type in (OptionType.ABILITY, OptionType.DISCARD):
        for index, option in enumerate(obs.select.option):
            if option.type != option_type:
                continue
            card = get_card(obs, option.area, option.index, info.my_index)
            if (
                isinstance(card, Pokemon)
                and info.my_active
                and card.serial == info.my_active.serial
                and card.id in FOSSILS
            ):
                return index

    for index, option in enumerate(obs.select.option):
        if option.type == OptionType.RETREAT:
            return index
    return None


def choose_lively_stadium_ability(obs: Observation, info: BoardInfo) -> int | None:
    if info.field_counts[COMFEY] > 0:
        return None
    for index, option in enumerate(obs.select.option):
        if option.type != OptionType.ABILITY:
            continue
        card = get_card(obs, option.area, option.index, info.my_index)
        if card is not None and card.id == LIVELY_STADIUM:
            return index
    return None


def choose_play_rough_attack(obs: Observation, info: BoardInfo) -> int | None:
    if not info.op_active:
        return None
    should_attack = (info.op_active.id == BUDEW and info.op_active.hp <= 40) or (
        info.op_active.hp <= 20
    )
    if not should_attack:
        return None
    for index, option in enumerate(obs.select.option):
        if option.type == OptionType.ATTACK and option.attackId == PLAY_ROUGH:
            return index
    return None


def flower_shower_attack_is_safe(obs: Observation, info: BoardInfo) -> bool:
    my_state = obs.current.players[info.my_index]
    op_state = obs.current.players[info.op_index]
    if not should_use_flower_shower(my_state.deckCount, op_state.deckCount):
        return False
    return not (
        info.my_active
        and info.my_active.id == COMFEY
        and not my_state.bench
        and op_state.deckCount > 3
        and opponent_can_ko_next_turn(info.my_active, info)
    )


def choose_flower_shower_attack(
    obs: Observation, info: BoardInfo, win_only: bool = False
) -> int | None:
    for index, option in enumerate(obs.select.option):
        if option.type != OptionType.ATTACK or option.attackId != FLOWER_SHOWER:
            continue
        if win_only:
            return index if terminal_action_can_win_now(obs, option, info) else None
        if flower_shower_attack_is_safe(obs, info):
            return index
    return None


def choose_end_option(obs: Observation) -> int | None:
    for index, option in enumerate(obs.select.option):
        if option.type == OptionType.END:
            return index
    return None


def has_recovery_target(info: BoardInfo) -> bool:
    return bool(
        info.discard_counts[COMFEY]
        or info.field_counts[COMFEY]
        or info.hand_counts[COMFEY]
        or info.discard_counts[BASIC_PSYCHIC_ENERGY]
    )


def choose_main_action_by_plan(obs: Observation, info: BoardInfo) -> list[int] | None:
    select = obs.select
    if select is None or select.context != SelectContext.MAIN:
        return None

    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]
    no_supporter = not state.supporterPlayed
    deck_safe = deck_is_safe_to_thin(my_state.deckCount, op_state.deckCount)
    deck_safe_for_two = deck_is_safe_to_thin(
        my_state.deckCount, op_state.deckCount, amount=2
    )
    need_energy = not info.active_has_attack_energy
    need_stadium = info.stadium_id not in STADIUMS
    need_backup = needs_fossil_access(info)
    restore_ready = comfey_restore_prepared(info, obs)

    option_index = choose_flower_shower_attack(obs, info, win_only=True)
    if option_index is not None:
        return [option_index]

    if info.bench_fossil_count == 0:
        option_index = choose_fossil_play_option(obs, info)
        if option_index is not None:
            return [option_index]
        if no_supporter:
            option_index = choose_play_option_for_ids(obs, info, [TEAM_ROCKETS_PETREL])
            if option_index is not None:
                return [option_index]
            if deck_safe_for_two:
                option_index = choose_play_option_for_ids(
                    obs, info, [CIPHERMANIACS_CODEBREAKING]
                )
                if option_index is not None:
                    return [option_index]
        if deck_safe:
            option_index = choose_play_option_for_ids(obs, info, [POKEGEAR])
            if option_index is not None:
                return [option_index]

    option_index = choose_play_option_for_ids(obs, info, [COMFEY])
    if option_index is not None and (
        info.field_counts[COMFEY] == 0
        or comfey_from_hand_can_attack_this_turn(info, obs)
    ):
        return [option_index]

    if recovered_comfey_can_attack_this_turn(info, obs):
        option_index = choose_play_option_for_ids(obs, info, [NIGHT_STRETCHER])
        if option_index is not None:
            return [option_index]
    if no_supporter and recovered_comfey_can_attack_this_turn(
        info, obs, include_basic_from_discard=True
    ):
        option_index = choose_play_option_for_ids(obs, info, [LANAS_AID])
        if option_index is not None:
            return [option_index]
    if no_supporter and petrel_to_stretcher_can_attack_this_turn(info, obs):
        option_index = choose_play_option_for_ids(obs, info, [TEAM_ROCKETS_PETREL])
        if option_index is not None:
            return [option_index]

    option_index = choose_attack_energy_attach_option(obs, info)
    if option_index is not None:
        return [option_index]

    if need_energy:
        if deck_safe:
            option_index = choose_play_option_for_ids(obs, info, [ENERGY_SEARCH])
            if option_index is not None:
                return [option_index]
        if info.discard_counts[BASIC_PSYCHIC_ENERGY]:
            option_index = choose_play_option_for_ids(obs, info, [ENERGY_RETRIEVAL])
            if option_index is not None:
                return [option_index]
        if no_supporter and deck_safe_for_two:
            option_index = choose_play_option_for_ids(obs, info, [COLRESS_TENACITY])
            if option_index is not None:
                return [option_index]

    if info.fossil_count < info.target_fossils:
        option_index = choose_fossil_play_option(obs, info)
        if option_index is not None:
            return [option_index]

    if need_stadium or info.opponent_stadium_in_play or info.tera_pressure:
        option_index = choose_stadium_play_option(obs, info)
        if option_index is not None:
            return [option_index]

    if not restore_ready and has_recovery_target(info):
        option_index = choose_play_option_for_ids(obs, info, [NIGHT_STRETCHER])
        if option_index is not None:
            return [option_index]
        if no_supporter:
            option_index = choose_play_option_for_ids(obs, info, [LANAS_AID])
            if option_index is not None:
                return [option_index]

    option_index = choose_lively_stadium_ability(obs, info)
    if option_index is not None:
        return [option_index]

    option_index = choose_clear_active_fossil_option(obs, info)
    if option_index is not None:
        return [option_index]

    if no_supporter and ciphermaniac_can_feed_flower_shower(info, obs):
        option_index = choose_play_option_for_ids(
            obs, info, [CIPHERMANIACS_CODEBREAKING]
        )
        if option_index is not None:
            return [option_index]

    if no_supporter and xerosic_disruption_is_live(info, obs):
        option_index = choose_play_option_for_ids(obs, info, [XEROSICS_MACHINATIONS])
        if option_index is not None:
            return [option_index]

    if info.best_trap_score > info.active_trap_score + 200:
        option_index = choose_play_option_for_ids(obs, info, [POKEMON_CATCHER])
        if option_index is not None:
            return [option_index]

    if op_state.handCount >= 7:
        option_index = choose_play_option_for_ids(obs, info, [HAND_TRIMMER])
        if option_index is not None:
            return [option_index]

    if no_supporter and (
        need_backup or need_energy or need_stadium or not restore_ready
    ):
        option_index = choose_play_option_for_ids(obs, info, [TEAM_ROCKETS_PETREL])
        if option_index is not None:
            return [option_index]

    if (
        no_supporter
        and deck_safe_for_two
        and (need_backup or need_energy or need_stadium)
    ):
        option_index = choose_play_option_for_ids(
            obs, info, [CIPHERMANIACS_CODEBREAKING]
        )
        if option_index is not None:
            return [option_index]

    if deck_safe and (
        (not no_supporter and need_backup)
        or (no_supporter and not any(info.hand_counts[cid] for cid in SUPPORTERS))
    ):
        option_index = choose_play_option_for_ids(obs, info, [POKEGEAR])
        if option_index is not None:
            return [option_index]

    option_index = choose_play_rough_attack(obs, info)
    if option_index is not None:
        return [option_index]

    option_index = choose_flower_shower_attack(obs, info)
    if option_index is not None:
        return [option_index]

    if (
        op_state.handCount >= 5
        and hand_trimmer_self_discard_count(my_state.handCount) == 0
    ):
        option_index = choose_play_option_for_ids(obs, info, [HAND_TRIMMER])
        if option_index is not None:
            return [option_index]

    option_index = choose_end_option(obs)
    if option_index is not None:
        return [option_index]
    return None


def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return MY_DECK

    info = build_board_info(obs)
    ciphermaniac_action = choose_ciphermaniac_stack_options(obs, info)
    if ciphermaniac_action is not None:
        return ciphermaniac_action

    planned_action = choose_main_action_by_plan(obs, info)
    if planned_action is not None:
        return planned_action

    scores = [
        score_option(i, option, info, obs) for i, option in enumerate(obs.select.option)
    ]
    return choose_by_scores(obs, scores)
