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
HAND_TRIMMER = 1087
ACCOMPANYING_FLUTE = 1091
NIGHT_STRETCHER = 1097
ROOT_FOSSIL = 1099
ENERGY_SEARCH = 1119
CRUSHING_HAMMER = 1120
POKEGEAR = 1122
POKEMON_CATCHER = 1124
COVER_FOSSIL = 1136
PLUME_FOSSIL = 1138
HANDHELD_FAN = 1161
GRAVITY_GEMSTONE = 1166
BOSS_ORDERS = 1182
LANAS_AID = 1184
ERI = 1186
COLRESS_TENACITY = 1194
XEROSICS_MACHINATIONS = 1197
NEUTRALIZATION_ZONE = 1247
LIVELY_STADIUM = 1251
BASIC_PSYCHIC_ENERGY = 5
MIST_ENERGY = 11

FLOWER_SHOWER = 215
PLAY_ROUGH = 216

FOSSILS = {ROOT_FOSSIL, COVER_FOSSIL, PLUME_FOSSIL}
ENERGY_CARDS = {BASIC_PSYCHIC_ENERGY, MIST_ENERGY}
SUPPORTERS = {
    BOSS_ORDERS,
    LANAS_AID,
    ERI,
    COLRESS_TENACITY,
    XEROSICS_MACHINATIONS,
}
STADIUMS = {NEUTRALIZATION_ZONE, LIVELY_STADIUM}

# Rough pressure estimates for common metagame attackers.
META_DAMAGE = {
    121: 260,  # Dragapult ex
    245: 140,  # Alakazam
    266: 999,  # Iono's Electrode
    269: 230,  # Iono's Bellibolt ex
    345: 120,  # Crustle
    361: 140,  # Misty's Starmie after evolving
    533: 140,  # Crustle
    678: 270,  # Mega Lucario ex
    723: 300,  # Mega Abomasnow ex
    743: 180,  # Alakazam
    1031: 210,  # Mega Starmie ex
}
BENCH_SNIPE_ATTACKERS = {121, 1031}
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
    active_has_mist: bool
    rule_box_pressure: bool
    neutralization_urgent: bool
    opponent_stadium_in_play: bool
    effect_pressure: bool
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
    return any(p.id in {121, 245, 743, 1031} for p in op_field)


def fossil_wall_lock_is_available(
    op_active: Pokemon | None, op_field: list[Pokemon], active_trap_score: int
) -> bool:
    if op_active is None or active_trap_score < 700:
        return False
    if next_turn_attack_damage(op_active) > 0:
        return False
    return not any(can_damage_bench_next_turn(pokemon) for pokemon in op_field)


def estimate_target_fossils(
    my_state, op_field: list[Pokemon], my_active: Pokemon | None
) -> int:
    if my_active is None:
        return 1

    bench_snipe = any(can_damage_bench_next_turn(pokemon) for pokemon in op_field)
    max_next_damage = max(
        (next_turn_attack_damage(pokemon) for pokemon in op_field), default=0
    )
    next_attack_can_ko = max_next_damage >= my_active.hp

    target = 1
    if not bench_snipe:
        target = 2
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
        active_has_mist=has_mist_energy(my_active),
        rule_box_pressure=opponent_has_rule_box_pressure(op_field),
        neutralization_urgent=neutralization_zone_is_urgent(
            my_state, op_state, op_active
        ),
        opponent_stadium_in_play=opponent_stadium_in_play,
        effect_pressure=opponent_has_effect_pressure(op_field),
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
        return 50000
    if my_after <= 0:
        return -30000

    score = 8500 + max(0, 15 - op_deck_count) * 450
    score += (my_deck_count - op_deck_count) * 120
    if my_after <= 3:
        score -= 1500
    return score


def own_card_keep_value(card_id: int, info: BoardInfo, my_state) -> int:
    if card_id == COMFEY:
        return 20000
    if card_id == BASIC_PSYCHIC_ENERGY:
        return 18000 if not info.active_has_basic_psychic else 2200
    if card_id == MIST_ENERGY:
        return 5200 if info.effect_pressure and not info.active_has_mist else 1200
    if card_id == GRAVITY_GEMSTONE:
        return 16000 if not info.active_has_gravity else 900
    if card_id == HANDHELD_FAN:
        if (
            info.my_active
            and not info.my_active.tools
            and not info.hand_counts[GRAVITY_GEMSTONE]
        ):
            return 6200
        return 700
    if card_id in FOSSILS:
        if info.bench_fossil_count == 0:
            return 9200
        if info.fossil_count < info.target_fossils:
            return 7500
        return 900
    if card_id == NIGHT_STRETCHER:
        return 9500 if info.discard_counts[COMFEY] else 3000
    if card_id == LANAS_AID:
        return 9000 if info.discard_counts[COMFEY] else 3600
    if card_id == BOSS_ORDERS:
        return 7600 if info.best_trap_score > info.active_trap_score + 120 else 3600
    if card_id == XEROSICS_MACHINATIONS:
        return 7200
    if card_id == ERI:
        return 6500
    if card_id == COLRESS_TENACITY:
        return 16000 if not info.active_has_basic_psychic else 4300
    if card_id == CRUSHING_HAMMER:
        return 6800
    if card_id == POKEMON_CATCHER:
        return 5600
    if card_id == HAND_TRIMMER:
        return 4700
    if card_id == POKEGEAR:
        return 2600
    if card_id == ACCOMPANYING_FLUTE:
        return 2300
    if card_id == ENERGY_SEARCH:
        return 15000 if not info.active_has_basic_psychic else 1000
    if card_id == NEUTRALIZATION_ZONE:
        if info.neutralization_urgent:
            return 14000
        return 9000 if info.rule_box_pressure else 3200
    if card_id == LIVELY_STADIUM:
        return 4100
    return 1000


def score_fossil_to_play(card_id: int, info: BoardInfo) -> int:
    needs_bench_backup = info.bench_fossil_count == 0
    if info.fossil_count >= info.target_fossils and not needs_bench_backup:
        return -600

    shortage = max(0, info.target_fossils - info.fossil_count)
    base = 10500 + shortage * 1200
    if needs_bench_backup:
        base += 4300
        if (
            info.my_active
            and info.my_active.id in FOSSILS
            and info.bench_comfey_count == 1
        ):
            base += 1600
    if card_id == PLUME_FOSSIL:
        return base + (700 if info.effect_pressure else 80)
    if card_id == COVER_FOSSIL:
        return base + (420 if info.effect_pressure else 140)
    if card_id == ROOT_FOSSIL:
        active_data = card_data(info.op_active.id) if info.op_active else None
        return base + (500 if active_data and active_data.basic else 120)
    return base


def score_play_card(card_id: int, info: BoardInfo, obs: Observation) -> int:
    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]
    op_has_energy = any(len(pokemon.energies) > 0 for pokemon in info.op_field)
    no_supporter = not state.supporterPlayed
    deck_safe = deck_is_safe_to_thin(my_state.deckCount, op_state.deckCount)

    if card_id == CRUSHING_HAMMER:
        return 9200 if op_has_energy else -900
    if card_id == XEROSICS_MACHINATIONS and no_supporter:
        return (
            9100 + max(0, op_state.handCount - 3) * 180
            if op_state.handCount > 3
            else -400
        )
    if card_id == ERI and no_supporter:
        if op_state.handCount >= 4:
            return 8900 + op_state.handCount * 80
        return 3400 if op_state.handCount >= 2 else -500
    if card_id == BOSS_ORDERS and no_supporter:
        improvement = info.best_trap_score - info.active_trap_score
        if improvement > 120:
            gravity_bonus = (
                550
                if info.active_has_gravity or info.hand_counts[GRAVITY_GEMSTONE]
                else 0
            )
            return 8600 + improvement + gravity_bonus
        return -700
    if card_id == POKEMON_CATCHER:
        improvement = info.best_trap_score - info.active_trap_score
        return 7600 + improvement if improvement > 160 else -600
    if card_id == HAND_TRIMMER:
        if op_state.handCount > 5 and my_state.handCount <= op_state.handCount:
            return 8200 + (op_state.handCount - 5) * 160
        return -800
    if card_id == NIGHT_STRETCHER:
        if info.discard_counts[COMFEY] and info.field_counts[COMFEY] == 0:
            return 9700
        if (
            info.discard_counts[BASIC_PSYCHIC_ENERGY]
            and not info.active_has_basic_psychic
        ):
            return 7600
        if info.discard_counts[COMFEY]:
            return 7200
        return -500
    if card_id == LANAS_AID and no_supporter:
        if info.discard_counts[COMFEY] and info.field_counts[COMFEY] == 0:
            return 9300
        recoverable = sum(
            info.discard_counts[cid] for cid in FOSSILS | ENERGY_CARDS | {COMFEY}
        )
        return 6200 + recoverable * 120 if recoverable >= 3 else -500
    if card_id in FOSSILS:
        return score_fossil_to_play(card_id, info)
    if card_id == GRAVITY_GEMSTONE:
        if info.my_active and not info.active_has_gravity and not info.my_active.tools:
            return 24000 if info.my_active.id == COMFEY else 21000
        return -600
    if card_id == HANDHELD_FAN:
        if (
            info.my_active
            and not info.my_active.tools
            and not info.hand_counts[GRAVITY_GEMSTONE]
        ):
            return 11200 if info.my_active.id == COMFEY else 9000
        return -900
    if card_id == ENERGY_SEARCH:
        if not info.active_has_basic_psychic and deck_safe:
            return 22000
        return -650
    if card_id == COLRESS_TENACITY and no_supporter:
        need_energy = not info.active_has_basic_psychic
        need_stadium = info.stadium_id not in {NEUTRALIZATION_ZONE, LIVELY_STADIUM}
        if deck_is_safe_to_thin(my_state.deckCount, op_state.deckCount, amount=2) and (
            need_energy or need_stadium
        ):
            return 20500 if need_energy else 6900 + (600 if need_stadium else 0)
        return -500
    if card_id == NEUTRALIZATION_ZONE:
        if info.stadium_id == NEUTRALIZATION_ZONE:
            return -900
        if info.neutralization_urgent:
            return 18500
        if info.opponent_stadium_in_play and info.rule_box_pressure:
            return 4200
        return -1200
    if card_id == LIVELY_STADIUM:
        if info.stadium_id == NEUTRALIZATION_ZONE:
            return -900
        if info.stadium_id != LIVELY_STADIUM:
            return 6100 if not info.rule_box_pressure else 3000
        return -700
    if card_id == POKEGEAR:
        has_supporter = any(info.hand_counts[cid] for cid in SUPPORTERS)
        if deck_safe and not info.active_has_basic_psychic:
            return 17000
        if deck_safe and not has_supporter:
            return 6400
        return -700
    if card_id == ACCOMPANYING_FLUTE:
        if len(op_state.bench) < op_state.benchMax and op_state.deckCount > 4:
            return 5600 + max(0, op_state.deckCount - my_state.deckCount) * 80
        return -900
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

    if card_id == BASIC_PSYCHIC_ENERGY:
        if target_is_comfey and not has_basic_psychic(target):
            return 23000 if active_target else 18000
        if target_is_comfey:
            return 1800
        return -800
    if card_id == MIST_ENERGY:
        if (
            target_is_comfey
            and has_basic_psychic(target)
            and not has_mist_energy(target)
        ):
            return 7000 if info.effect_pressure else 3600
        if target_is_comfey and not has_basic_psychic(target):
            return 900
        return -700
    if card_id == GRAVITY_GEMSTONE:
        if not target.tools and active_target:
            return 28000 if target_is_comfey else 23000
        if not target.tools and target_is_comfey:
            return 14000
        return -800
    if card_id == HANDHELD_FAN:
        if (
            not target.tools
            and active_target
            and not info.hand_counts[GRAVITY_GEMSTONE]
        ):
            return 12500 if target_is_comfey else 9500
        return -900
    if card_id in ENERGY_CARDS and target.id in FOSSILS:
        return -900
    return -500


def score_to_active(card: Pokemon | Card | None, info: BoardInfo) -> int:
    if not isinstance(card, Pokemon):
        return -1000
    if card.id == COMFEY:
        score = 10000
        if has_basic_psychic(card):
            score += 900
        if has_gravity(card):
            score += 450
        return score
    if card.id == COVER_FOSSIL:
        return 6200 if info.effect_pressure else 5200
    if card.id == ROOT_FOSSIL:
        active_data = card_data(info.op_active.id) if info.op_active else None
        return 6100 if active_data and active_data.basic else 5000
    if card.id == PLUME_FOSSIL:
        return 5000
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
        return -5200
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


def score_to_hand(
    card: Pokemon | Card | None, info: BoardInfo, obs: Observation
) -> int:
    if card is None:
        return -1000

    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]
    card_id = card.id

    if card_id == COMFEY:
        return 20000 if info.field_counts[COMFEY] == 0 else 9000
    if card_id == BASIC_PSYCHIC_ENERGY:
        return 19000 if not info.active_has_basic_psychic else 5600
    if card_id == MIST_ENERGY:
        return 7200 if info.effect_pressure and not info.active_has_mist else 1600
    if card_id == NEUTRALIZATION_ZONE:
        if info.neutralization_urgent and info.stadium_id != NEUTRALIZATION_ZONE:
            return 12500
        if info.opponent_stadium_in_play and info.rule_box_pressure:
            return 5200
        return 2600
    if card_id == LIVELY_STADIUM:
        return 6500 if info.stadium_id not in STADIUMS else 2800
    if card_id == XEROSICS_MACHINATIONS:
        return 8600 + op_state.handCount * 80 if op_state.handCount > 3 else 3300
    if card_id == ERI:
        return 8100 if op_state.handCount >= 4 else 3800
    if card_id == BOSS_ORDERS:
        return 8300 if info.best_trap_score > info.active_trap_score + 120 else 3600
    if card_id == LANAS_AID:
        return 8000 if info.discard_counts[COMFEY] else 2500
    if card_id == COLRESS_TENACITY:
        need_energy = not info.active_has_basic_psychic
        need_stadium = info.stadium_id == 0
        return 18500 if need_energy else 6800 if need_stadium else 2500
    if card_id == NIGHT_STRETCHER:
        return 8600 if info.discard_counts[COMFEY] else 2400
    if card_id in FOSSILS:
        if info.bench_fossil_count == 0:
            return 9400
        return 7200 if info.fossil_count < info.target_fossils else 1500
    if card_id == GRAVITY_GEMSTONE:
        return 18000 if not info.active_has_gravity else 1600
    if card_id == CRUSHING_HAMMER:
        return 7200 if any(len(p.energies) for p in info.op_field) else 1800
    if card_id == ENERGY_SEARCH:
        if not info.active_has_basic_psychic and deck_is_safe_to_thin(
            my_state.deckCount, op_state.deckCount
        ):
            return 17000
        return (
            5200
            if deck_is_safe_to_thin(my_state.deckCount, op_state.deckCount)
            else -300
        )
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
            score += 5000
        if card_id in {1123, 1126, 1102, 1121, 1086, 1118, 1120, 1124}:
            score += 1800
        if card_id in ENERGY_CARDS:
            score += 900
        if data and data.cardType == CardType.SUPPORTER:
            score += 700
        return score

    keep = own_card_keep_value(card_id, info, my_state)
    duplicates = max(0, info.hand_counts[card_id] - 1)
    score = 10000 - keep + duplicates * 1000
    if card_id in {ACCOMPANYING_FLUTE, POKEGEAR} and not deck_is_safe_to_thin(
        my_state.deckCount, state.players[info.op_index].deckCount
    ):
        score += 1200
    if card_id == MIST_ENERGY and info.hand_counts[BASIC_PSYCHIC_ENERGY]:
        score += 800
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

    if pokemon.id == COMFEY and has_basic_psychic(pokemon):
        return -3000
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

    if has_benched_fossil_after_clear:
        score = 7400
    elif can_rebuild_backup:
        score = 5200
    else:
        score = -1600

    if op_state.deckCount <= 3 and has_basic_psychic(comfey):
        score += 14000

    if not can_rebuild_backup:
        incoming = max(
            (next_turn_attack_damage(pokemon) for pokemon in info.op_field), default=0
        )
        if incoming >= comfey.hp:
            score -= 3600
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
        score = 5000
        if not has_basic_psychic(target):
            score += 4500
        if not has_gravity(target):
            score += 1200
        return score
    if target.id in FOSSILS:
        return 1000
    return 0


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
            return 12000
        if card is not None and card.id in FOSSILS:
            return score_fossil_to_play(card.id, info)
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
    op_deck_count = obs.current.players[info.op_index].deckCount

    if context == SelectContext.DRAW_COUNT:
        if my_deck_count <= op_deck_count + 2:
            return -number * 500
        return number * 120
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
        if info.active_has_gravity:
            score += 2500
        return score
    if option.attackId == PLAY_ROUGH:
        if info.op_active and info.op_active.hp <= 20:
            return 900
        return -1200
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
            if info.fossil_count > info.target_fossils and info.bench_fossil_count > 1:
                return 900
            return -700
        if card.id == LIVELY_STADIUM:
            return 400
        return -500
    if option.type == OptionType.DISCARD:
        card = get_card(obs, option.area, option.index, info.my_index)
        if isinstance(card, Pokemon) and card.id in FOSSILS:
            if info.my_active and info.my_active.serial == card.serial:
                return score_clear_active_fossil(info, obs)
            if info.fossil_count > info.target_fossils and info.bench_fossil_count > 1:
                return 1800
        return -800
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
        score = 200
        if not should_use_flower_shower(my_state.deckCount, op_state.deckCount):
            score += 1200
        if info.active_has_gravity and info.active_trap_score > 150:
            score += 500
        return score
    if option.type == OptionType.SKILL:
        return 100
    if option.type == OptionType.SPECIAL_CONDITION:
        return 0
    return 0


def has_pending_setup_before_terminal_action(
    obs: Observation, info: BoardInfo, scores: list[int]
) -> bool:
    select = obs.select
    if select.context != SelectContext.MAIN:
        return False

    for index, option in enumerate(select.option):
        if option.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, option.index, info.my_index)
            if (
                isinstance(card, Card)
                and card.id in FOSSILS
                and (
                    info.fossil_count < info.target_fossils
                    or info.bench_fossil_count == 0
                )
                and scores[index] > 0
            ):
                return True
        elif option.type == OptionType.ATTACH:
            card_owner = (
                option.playerIndex if option.playerIndex is not None else info.my_index
            )
            card = get_card(obs, option.area, option.index, card_owner)
            if isinstance(card, Card) and card.id in {GRAVITY_GEMSTONE, HANDHELD_FAN}:
                if scores[index] > 0:
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


def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return MY_DECK

    info = build_board_info(obs)
    scores = [
        score_option(i, option, info, obs) for i, option in enumerate(obs.select.option)
    ]
    execution_scores = order_scores_for_execution(obs, info, scores)
    return choose_by_scores(obs, execution_scores)
