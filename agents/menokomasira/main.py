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

# Deck core.
BASIC_WATER = 3
BASIC_PSYCHIC = 5
BASIC_DARK = 7
TELEPATH_PSYCHIC = 19

BRONZONG = 55
FROSLASS = 104
MUNKIDORI = 112
BRONZOR = 335
SNORUNT = 860
MEGA_FROSLASS_EX = 861
MEOWTH_EX = 1071

BUDDY_BUDDY_POFFIN = 1086
SECRET_BOX = 1092
NIGHT_STRETCHER = 1097
CALL_BELL = 1101
ENERGY_SEARCH = 1119
ULTRA_BALL = 1121
POKE_PAD = 1152
AIR_BALLOON = 1174
BOSSS_ORDERS = 1182
LANAS_AID = 1184
SALVATORE = 1189
CRISPIN = 1198
BROCKS_SCOUTING = 1210
HILDA = 1225
LILLIES_DETERMINATION = 1227

EVOLUTION_JAMMER = 58
SUPER_PSY_BOLT = 59
FROST_SMASH = 131
MIND_BEND = 141
CHILLY = 1239
RESENTFUL_REFRAIN = 1240
ABSOLUTE_SNOW = 1241
TUCK_TAIL = 1546

BASIC_POKEMON = {SNORUNT, BRONZOR, MUNKIDORI, MEOWTH_EX}
SETUP_BASICS = {SNORUNT, BRONZOR, MUNKIDORI}
EVOLUTIONS = {FROSLASS, MEGA_FROSLASS_EX, BRONZONG}
ATTACKERS = {MEGA_FROSLASS_EX, BRONZONG, MUNKIDORI, FROSLASS, SNORUNT}
ENERGY_CARDS = {BASIC_WATER, BASIC_PSYCHIC, BASIC_DARK, TELEPATH_PSYCHIC}
BASIC_ENERGY = {BASIC_WATER, BASIC_PSYCHIC, BASIC_DARK}
SUPPORTERS = {
    BOSSS_ORDERS,
    LANAS_AID,
    SALVATORE,
    CRISPIN,
    BROCKS_SCOUTING,
    HILDA,
    LILLIES_DETERMINATION,
}
ITEMS = {
    BUDDY_BUDDY_POFFIN,
    SECRET_BOX,
    NIGHT_STRETCHER,
    CALL_BELL,
    ENERGY_SEARCH,
    ULTRA_BALL,
    POKE_PAD,
}
TOOLS = {AIR_BALLOON}
NON_RULE_BOX_POKEMON = {SNORUNT, BRONZOR, MUNKIDORI, FROSLASS, BRONZONG}

FROSLASS_LINE_TARGET = 3
NORMAL_FROSLASS_TARGET = 2
BRONZONG_TARGET = 1
MUNKIDORI_TARGET = 2
MUNKIDORI_PRESSURE_TARGET = 3


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
    stadium_id: int


# ---------- General state helpers ----------


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
    if area is None or index is None or obs.current is None:
        return None
    state = obs.current
    try:
        if area == AreaType.DECK:
            if obs.select is None or obs.select.deck is None:
                return None
            return obs.select.deck[index]
        if area == AreaType.HAND:
            hand = state.players[player_index].hand
            return None if hand is None else hand[index]
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
            return None if state.looking is None else state.looking[index]
    except (IndexError, TypeError):
        return None
    return None


def card_data(card_id: int):
    return CARD_TABLE.get(card_id)


def energy_card_ids(pokemon: Pokemon | None) -> set[int]:
    if pokemon is None:
        return set()
    return {energy.id for energy in pokemon.energyCards}


def energy_count(pokemon: Pokemon | None) -> int:
    if pokemon is None:
        return 0
    return len(pokemon.energyCards)


def has_water(pokemon: Pokemon | None) -> bool:
    return BASIC_WATER in energy_card_ids(pokemon)


def has_dark(pokemon: Pokemon | None) -> bool:
    return BASIC_DARK in energy_card_ids(pokemon)


def has_psychic(pokemon: Pokemon | None) -> bool:
    return bool(energy_card_ids(pokemon) & {BASIC_PSYCHIC, TELEPATH_PSYCHIC})


def has_air_balloon(pokemon: Pokemon | None) -> bool:
    if pokemon is None:
        return False
    return any(tool.id == AIR_BALLOON for tool in pokemon.tools)


def damage_on(pokemon: Pokemon | None) -> int:
    if pokemon is None:
        return 0
    return max(0, pokemon.maxHp - pokemon.hp)


def is_rule_box_card_id(card_id: int) -> bool:
    data = card_data(card_id)
    return bool(data and (data.ex or data.megaEx or data.tera))


def is_rule_box(pokemon: Pokemon | None) -> bool:
    return bool(pokemon and is_rule_box_card_id(pokemon.id))


def build_board_info(obs: Observation) -> BoardInfo:
    state = obs.current
    my_index = state.yourIndex
    op_index = 1 - my_index
    my_state = state.players[my_index]
    op_state = state.players[op_index]
    my_field = in_play_pokemon(my_state)
    op_field = in_play_pokemon(op_state)
    hand = my_state.hand or []
    stadium_id = state.stadium[0].id if state.stadium else 0
    return BoardInfo(
        my_index=my_index,
        op_index=op_index,
        my_active=active_pokemon(my_state),
        op_active=active_pokemon(op_state),
        my_field=my_field,
        op_field=op_field,
        hand_counts=Counter(card.id for card in hand),
        discard_counts=Counter(card.id for card in my_state.discard),
        field_counts=Counter(pokemon.id for pokemon in my_field),
        stadium_id=stadium_id,
    )


def deck_is_safe_to_search(
    my_deck_count: int, op_deck_count: int, amount: int = 1
) -> bool:
    if my_deck_count - amount <= 0:
        return False
    return my_deck_count - amount >= min(3, op_deck_count - 8)


# ---------- Deck plan helpers ----------


def wants_snorunt(info: BoardInfo) -> bool:
    return froslass_line_count(info) < FROSLASS_LINE_TARGET


def wants_bronzor(info: BoardInfo) -> bool:
    return info.field_counts[BRONZOR] + info.field_counts[BRONZONG] < BRONZONG_TARGET


def wants_munkidori(info: BoardInfo) -> bool:
    if info.field_counts[MUNKIDORI] < MUNKIDORI_TARGET:
        return True
    return (
        info.field_counts[FROSLASS] >= NORMAL_FROSLASS_TARGET
        and info.field_counts[MUNKIDORI] < MUNKIDORI_PRESSURE_TARGET
    )


def froslass_line_count(info: BoardInfo) -> int:
    return (
        info.field_counts[SNORUNT]
        + info.field_counts[FROSLASS]
        + info.field_counts[MEGA_FROSLASS_EX]
    )


def wants_normal_froslass(info: BoardInfo) -> bool:
    return (
        info.field_counts[SNORUNT] > 0
        and info.field_counts[FROSLASS] < NORMAL_FROSLASS_TARGET
    )


def wants_mega_froslass(info: BoardInfo) -> bool:
    return info.field_counts[SNORUNT] > 0 and info.field_counts[MEGA_FROSLASS_EX] == 0


def wants_bronzong(info: BoardInfo) -> bool:
    return info.field_counts[BRONZOR] > 0 and info.field_counts[BRONZONG] == 0


def powered_munkidori_count(info: BoardInfo) -> int:
    return sum(
        1 for pokemon in info.my_field if pokemon.id == MUNKIDORI and has_dark(pokemon)
    )


def snorunt_access_count(info: BoardInfo) -> int:
    return info.field_counts[SNORUNT] + info.hand_counts[SNORUNT]


def froslass_line_access_count(info: BoardInfo) -> int:
    return froslass_line_count(info) + info.hand_counts[SNORUNT]


def normal_froslass_access_count(info: BoardInfo) -> int:
    return info.field_counts[FROSLASS] + info.hand_counts[FROSLASS]


def bronzor_access_count(info: BoardInfo) -> int:
    return info.field_counts[BRONZOR] + info.hand_counts[BRONZOR]


def bronzong_access_count(info: BoardInfo) -> int:
    return info.field_counts[BRONZONG] + info.hand_counts[BRONZONG]


def bronzong_line_access_count(info: BoardInfo) -> int:
    return (
        info.field_counts[BRONZOR]
        + info.field_counts[BRONZONG]
        + info.hand_counts[BRONZOR]
    )


def munkidori_access_count(info: BoardInfo) -> int:
    return info.field_counts[MUNKIDORI] + info.hand_counts[MUNKIDORI]


def wants_munkidori_from_search(info: BoardInfo) -> bool:
    access = munkidori_access_count(info)
    if access < MUNKIDORI_TARGET:
        return True
    return (
        normal_froslass_access_count(info) >= NORMAL_FROSLASS_TARGET
        and access < MUNKIDORI_PRESSURE_TARGET
    )


def support_search_needed(info: BoardInfo, obs: Observation) -> bool:
    if any(info.hand_counts[cid] for cid in SUPPORTERS):
        return False
    if obs.current.supporterPlayed:
        return False
    return bool(
        key_evolution_needed(info)
        or key_energy_needed(info)
        or wants_snorunt(info)
        or wants_bronzor(info)
        or wants_munkidori(info)
        or obs.current.players[info.my_index].handCount <= 4
    )


def active_bronzor_needs_backup(info: BoardInfo, obs: Observation) -> bool:
    if info.my_active is None or info.my_active.id != BRONZOR:
        return False
    if info.field_counts[BRONZONG] or info.field_counts[BRONZOR] > 1:
        return False
    if damage_on(info.my_active) >= 30 or info.my_active.hp <= 40:
        return True
    my_state = obs.current.players[info.my_index]
    has_other_board = any(
        pokemon.id != BRONZOR for pokemon in in_play_pokemon(my_state)
    )
    has_other_basic_in_hand = any(info.hand_counts[cid] for cid in {SNORUNT, MUNKIDORI})
    return not has_other_board and not has_other_basic_in_hand


def wants_bronzor_from_hand(info: BoardInfo, obs: Observation) -> bool:
    if wants_bronzor(info):
        return True
    return active_bronzor_needs_backup(info, obs)


def wants_basic(card_id: int, info: BoardInfo) -> bool:
    if card_id == SNORUNT:
        return wants_snorunt(info)
    if card_id == BRONZOR:
        return wants_bronzor(info)
    if card_id == MUNKIDORI:
        return wants_munkidori(info)
    if card_id == MEOWTH_EX:
        return not any(info.hand_counts[cid] for cid in SUPPORTERS)
    return False


def setup_priority(card_id: int, info: BoardInfo) -> int:
    if card_id == SNORUNT:
        return 9000 if wants_snorunt(info) else 2500
    if card_id == BRONZOR:
        return 7600 if wants_bronzor(info) else -800
    if card_id == MUNKIDORI:
        if info.field_counts[MUNKIDORI] < MUNKIDORI_TARGET:
            return 8200
        return 5600 if wants_munkidori(info) else 1400
    if card_id == MEOWTH_EX:
        return -2500
    return 0


def score_basic_play_card(card_id: int, info: BoardInfo, obs: Observation) -> int:
    if card_id == MEOWTH_EX:
        return 9800 if support_search_needed(info, obs) else -2500
    if card_id == BRONZOR:
        if wants_bronzor(info):
            return 7600
        return 3600 if active_bronzor_needs_backup(info, obs) else -900
    return setup_priority(card_id, info)


def evolution_priority(card_id: int, info: BoardInfo) -> int:
    if card_id == FROSLASS:
        if info.field_counts[FROSLASS] == 0:
            return 26000
        if info.field_counts[FROSLASS] < NORMAL_FROSLASS_TARGET:
            return 20500
        return 6500
    if card_id == MEGA_FROSLASS_EX:
        if info.field_counts[MEGA_FROSLASS_EX] == 0:
            return 23000 if info.field_counts[FROSLASS] else 21500
        return 6000
    if card_id == BRONZONG:
        if info.field_counts[BRONZONG] == 0:
            return 22000
        return 3500
    return 0


def key_evolution_needed(info: BoardInfo) -> bool:
    return bool(
        wants_normal_froslass(info) or wants_mega_froslass(info) or wants_bronzong(info)
    )


def key_energy_needed(info: BoardInfo) -> bool:
    return bool(
        any(p.id == MUNKIDORI and not has_dark(p) for p in info.my_field)
        or any(
            p.id in {SNORUNT, FROSLASS, MEGA_FROSLASS_EX} and not has_water(p)
            for p in info.my_field
        )
        or any(p.id == BRONZONG and not has_psychic(p) for p in info.my_field)
    )


def froslass_engine_online(info: BoardInfo) -> bool:
    return (
        info.field_counts[FROSLASS] >= NORMAL_FROSLASS_TARGET
        and powered_munkidori_count(info) >= 1
    )


def has_damaged_own_pokemon(info: BoardInfo) -> bool:
    return any(damage_on(pokemon) > 0 for pokemon in info.my_field)


def adrena_brain_ready(info: BoardInfo) -> bool:
    return any(
        pokemon.id == MUNKIDORI and has_dark(pokemon) for pokemon in info.my_field
    )


def opponent_has_evolution_in_play(info: BoardInfo) -> bool:
    return any(not card_data(p.id).basic for p in info.op_field if card_data(p.id))


def opponent_has_bench(info: BoardInfo, obs: Observation) -> bool:
    return bool(obs.current.players[info.op_index].bench)


def can_use_supporter(obs: Observation) -> bool:
    return not obs.current.supporterPlayed


def can_play_more_bench(obs: Observation, info: BoardInfo) -> bool:
    my_state = obs.current.players[info.my_index]
    return len(my_state.bench) < my_state.benchMax


def best_attack_damage(info: BoardInfo) -> int:
    active = info.my_active
    op_state = None
    if active is None:
        return 0
    if active.id == MEGA_FROSLASS_EX:
        # Resentful Refrain is usually the main attack; caller adds hand count.
        return 0
    if active.id == BRONZONG:
        return (
            100
            if has_psychic(active) and energy_count(active) >= 3
            else 30 if has_psychic(active) else 0
        )
    if active.id == FROSLASS:
        return 60 if has_water(active) and energy_count(active) >= 2 else 0
    if active.id == MUNKIDORI:
        return 60 if has_psychic(active) and energy_count(active) >= 2 else 0
    if active.id == SNORUNT:
        return 10 if has_water(active) else 0
    return 0


# ---------- Main-action scoring ----------


def score_play_card(card_id: int, info: BoardInfo, obs: Observation) -> int:
    state = obs.current
    my_state = state.players[info.my_index]
    op_state = state.players[info.op_index]
    deck_safe = deck_is_safe_to_search(my_state.deckCount, op_state.deckCount)

    if card_id in BASIC_POKEMON:
        if not can_play_more_bench(obs, info):
            return -500
        return score_basic_play_card(card_id, info, obs)

    if card_id == BUDDY_BUDDY_POFFIN:
        missing = int(wants_snorunt(info)) + int(wants_bronzor(info))
        if missing and can_play_more_bench(obs, info) and deck_safe:
            return 20000 + missing * 1200
        return -400

    if card_id == POKE_PAD:
        if deck_safe and wants_normal_froslass(info):
            return 18500
        if deck_safe and (
            wants_bronzong(info) or wants_munkidori(info) or wants_snorunt(info)
        ):
            return 16500
        return 2200 if deck_safe else -300

    if card_id == ULTRA_BALL:
        if my_state.handCount >= 4 and (
            key_evolution_needed(info) or wants_munkidori(info)
        ):
            return 17500 if wants_normal_froslass(info) else 16200
        return -300

    if card_id == SECRET_BOX:
        if my_state.handCount >= 5 and (
            key_evolution_needed(info) or key_energy_needed(info)
        ):
            return 16600
        return -600

    if card_id == NIGHT_STRETCHER:
        if info.discard_counts[FROSLASS] and wants_normal_froslass(info):
            return 18200
        if info.discard_counts[MUNKIDORI] and wants_munkidori(info):
            return 17600
        if info.discard_counts[SNORUNT] and wants_snorunt(info):
            return 15800
        if any(info.discard_counts[eid] for eid in BASIC_ENERGY) and key_energy_needed(
            info
        ):
            return 13800
        if info.discard_counts[BRONZONG] and wants_bronzong(info):
            return 12600
        return -300

    if card_id == ENERGY_SEARCH:
        return 12000 if key_energy_needed(info) and deck_safe else -200

    if card_id == CALL_BELL:
        if deck_safe and not any(info.hand_counts[cid] for cid in SUPPORTERS):
            return 14000
        return -500

    if card_id == AIR_BALLOON:
        if info.my_active and not has_air_balloon(info.my_active):
            return 7600 if info.my_active.id not in ATTACKERS else 4600
        return 2600 if any(not has_air_balloon(p) for p in info.my_field) else -400

    if card_id == SALVATORE and can_use_supporter(obs):
        if wants_bronzong(info) and not has_psychic(info.my_active):
            return 23800
        if wants_mega_froslass(info):
            return 23200
        if wants_bronzong(info):
            return 22600
        return 7200 if key_evolution_needed(info) else -500

    if card_id == HILDA and can_use_supporter(obs):
        if wants_normal_froslass(info) and key_energy_needed(info):
            return 23600
        if key_evolution_needed(info) and key_energy_needed(info):
            return 22400
        return 15200 if key_evolution_needed(info) or key_energy_needed(info) else -400

    if card_id == CRISPIN and can_use_supporter(obs):
        if any(p.id == MUNKIDORI and not has_dark(p) for p in info.my_field):
            return 23000
        return 21600 if key_energy_needed(info) else 4200

    if card_id == BROCKS_SCOUTING and can_use_supporter(obs):
        if wants_snorunt(info) or wants_bronzor(info) or wants_munkidori(info):
            return 18800
        return 15000 if key_evolution_needed(info) else -300

    if card_id == LILLIES_DETERMINATION and can_use_supporter(obs):
        if my_state.handCount <= 3 or (not info.my_field and my_state.handCount <= 5):
            return 19000
        if not key_evolution_needed(info) and not key_energy_needed(info):
            return 9000
        return 2500

    if card_id == LANAS_AID and can_use_supporter(obs):
        recoverable = sum(
            info.discard_counts[cid] for cid in NON_RULE_BOX_POKEMON | BASIC_ENERGY
        )
        if info.discard_counts[FROSLASS] and wants_normal_froslass(info):
            return 19400 + recoverable * 700
        if info.discard_counts[MUNKIDORI] and wants_munkidori(info):
            return 18400 + recoverable * 700
        if recoverable >= 2 and (key_energy_needed(info) or key_evolution_needed(info)):
            return 16200 + recoverable * 800
        return 11500 + recoverable * 500 if recoverable >= 3 else -400

    if card_id == BOSSS_ORDERS and can_use_supporter(obs):
        if opponent_has_bench(info, obs) and best_attack_damage(info) >= 60:
            return 12500
        return -400

    return -500


def score_evolve_option(option: Option, info: BoardInfo, obs: Observation) -> int:
    card = get_card(obs, option.area, option.index, info.my_index)
    target = get_card(obs, option.inPlayArea, option.inPlayIndex, info.my_index)
    if not isinstance(card, Card) or not isinstance(target, Pokemon):
        return -1000
    score = evolution_priority(card.id, info)
    if card.id == MEGA_FROSLASS_EX and target.id == SNORUNT:
        score += 2600
        if info.field_counts[FROSLASS] >= 1:
            score += 1800
    if card.id == FROSLASS and target.id == SNORUNT:
        score += 2600
        if info.field_counts[FROSLASS] == 0:
            score += 2600
    if card.id == BRONZONG and target.id == BRONZOR:
        score += 2200
        if any(
            card_data(p.id) and card_data(p.id).basic
            for p in obs.current.players[info.op_index].bench
        ):
            score += 2200
    return score if score else -500


def score_attach_option(option: Option, info: BoardInfo, obs: Observation) -> int:
    attach_card = get_card(
        obs, option.area, option.index, option.playerIndex or info.my_index
    )
    target = get_card(obs, option.inPlayArea, option.inPlayIndex, info.my_index)
    if not isinstance(attach_card, Card) or not isinstance(target, Pokemon):
        return -1000
    card_id = attach_card.id

    if card_id == BASIC_DARK:
        if target.id == MUNKIDORI and not has_dark(target):
            return 34500 if powered_munkidori_count(info) == 0 else 29200
        return 2500 if target.id == MUNKIDORI else -300

    if card_id == BASIC_WATER:
        if target.id == MEGA_FROSLASS_EX and not has_water(target):
            return 30500
        if target.id == FROSLASS and not has_water(target):
            return 23800 if target == info.my_active else 20400
        if target.id == SNORUNT and not has_water(target):
            return 22600
        if target.id == MEGA_FROSLASS_EX and energy_count(target) < 3:
            return 9000
        return -300

    if card_id in {BASIC_PSYCHIC, TELEPATH_PSYCHIC}:
        if target.id == BRONZONG and not has_psychic(target):
            return 28200
        if target.id == MUNKIDORI and not has_psychic(target):
            return 17200
        if (
            card_id == TELEPATH_PSYCHIC
            and target.id == MUNKIDORI
            and can_play_more_bench(obs, info)
        ):
            return 18500
        return -200

    if card_id == AIR_BALLOON:
        if not has_air_balloon(target):
            return (
                6000
                if target.id == (info.my_active.id if info.my_active else 0)
                else 2600
            )
        return -300

    return -500


def score_ability_option(option: Option, info: BoardInfo, obs: Observation) -> int:
    card = get_card(obs, option.area, option.index, info.my_index)
    if not isinstance(card, Pokemon):
        return -1000
    if card.id == MUNKIDORI:
        if has_dark(card) and has_damaged_own_pokemon(info):
            return 42000
        return -500
    if card.id == MEOWTH_EX:
        if not any(info.hand_counts[cid] for cid in SUPPORTERS) or key_evolution_needed(
            info
        ):
            return 26000
        return 5000
    return -500


def score_attack(option: Option, info: BoardInfo, obs: Observation) -> int:
    op_state = obs.current.players[info.op_index]
    active = info.my_active
    if active is None:
        return -1000

    if option.attackId == RESENTFUL_REFRAIN:
        return 26000 + op_state.handCount * 2500
    if option.attackId == ABSOLUTE_SNOW:
        return 33000
    if option.attackId == EVOLUTION_JAMMER:
        score = 30000
        if any(card_data(p.id) and card_data(p.id).basic for p in op_state.bench):
            score += 4000
        if not opponent_has_evolution_in_play(info):
            score += 2500
        return score
    if option.attackId == SUPER_PSY_BOLT:
        return 25000
    if option.attackId == MIND_BEND:
        return 20500
    if option.attackId == FROST_SMASH:
        return 17000
    if option.attackId == CHILLY:
        return 5000
    if option.attackId == TUCK_TAIL:
        return -1000
    return -500


def score_switch_to_active(card: Pokemon | Card | None, info: BoardInfo) -> int:
    if not isinstance(card, Pokemon):
        return -1000
    if card.id == MEGA_FROSLASS_EX and has_water(card):
        return 26000
    if card.id == BRONZONG and has_psychic(card):
        return 23000
    if card.id == MUNKIDORI and (has_dark(card) or has_psychic(card)):
        return 16000
    if card.id == FROSLASS and has_water(card):
        return 13000
    if card.id == SNORUNT and has_water(card):
        return 5000
    return 1000 - energy_count(card) * 50


# ---------- Search/discard/target scoring ----------


def score_to_hand(
    card: Pokemon | Card | None, info: BoardInfo, obs: Observation
) -> int:
    if card is None:
        return -1000
    card_id = card.id
    effect_id = obs.select.effect.id if obs.select and obs.select.effect else 0
    state = obs.current
    op_state = state.players[info.op_index]

    if effect_id == BUDDY_BUDDY_POFFIN:
        if card_id == SNORUNT:
            return 30000 if wants_snorunt(info) else 9000
        if card_id == BRONZOR:
            if wants_bronzor(info):
                return 26000
            return 13000 if active_bronzor_needs_backup(info, obs) else -800
        return -1000

    if effect_id == POKE_PAD:
        return score_poke_pad_to_hand(card_id, info, obs)

    if effect_id == ULTRA_BALL:
        if card_id == FROSLASS:
            if info.field_counts[FROSLASS] == 0:
                return 34500
            return (
                30200 if info.field_counts[FROSLASS] < NORMAL_FROSLASS_TARGET else 7200
            )
        if card_id == MEGA_FROSLASS_EX:
            return 32600 if info.field_counts[MEGA_FROSLASS_EX] == 0 else 9000
        if card_id == BRONZONG:
            return 29600 if info.field_counts[BRONZONG] == 0 else 6500
        if card_id == MUNKIDORI:
            return 24600 if wants_munkidori(info) else 3600
        if card_id == SNORUNT:
            return 21400 if wants_snorunt(info) else 3000
        if card_id == BRONZOR:
            return 19400 if wants_bronzor(info) else 2500
        return -800

    if effect_id == MEOWTH_EX or effect_id == CALL_BELL:
        return score_supporter_to_hand(card_id, info, obs)

    if effect_id == HILDA:
        if card_id in EVOLUTIONS:
            return 34000 + evolution_priority(card_id, info)
        if card_id == BASIC_DARK and any(
            p.id == MUNKIDORI and not has_dark(p) for p in info.my_field
        ):
            return 33000
        if card_id == BASIC_WATER and any(
            p.id in {SNORUNT, FROSLASS, MEGA_FROSLASS_EX} and not has_water(p)
            for p in info.my_field
        ):
            return 31500
        if card_id in {BASIC_PSYCHIC, TELEPATH_PSYCHIC}:
            return 26000
        return score_to_hand_generic(card_id, info, obs)

    if effect_id == BROCKS_SCOUTING:
        if card_id == MEOWTH_EX:
            return 15000 if support_search_needed(info, obs) else -700
        if card_id == BRONZOR:
            return 23600 if wants_bronzor_from_hand(info, obs) else -500
        if card_id in BASIC_POKEMON:
            return setup_priority(card_id, info) + 16000
        if card_id in EVOLUTIONS:
            return evolution_priority(card_id, info) + 12000
        return -600

    if effect_id == CRISPIN or effect_id == ENERGY_SEARCH:
        return score_energy_to_hand(card_id, info)

    if effect_id in {NIGHT_STRETCHER, LANAS_AID}:
        if card_id == FROSLASS and wants_normal_froslass(info):
            return 33000
        if card_id == MUNKIDORI and wants_munkidori(info):
            return 31000
        if card_id == SNORUNT and wants_snorunt(info):
            return 27600
        if card_id == BRONZONG and wants_bronzong(info):
            return 26500
        if card_id == BRONZOR and wants_bronzor(info):
            return 23600
        if card_id in {BASIC_DARK, BASIC_WATER, BASIC_PSYCHIC} and key_energy_needed(
            info
        ):
            return 24800
        if card_id in NON_RULE_BOX_POKEMON:
            return 12000
        return 1000

    if effect_id == SECRET_BOX:
        data = card_data(card_id)
        if card_id == ULTRA_BALL:
            return 26000
        if card_id == POKE_PAD:
            return 25000
        if card_id == AIR_BALLOON:
            return 16000
        if card_id in SUPPORTERS:
            return score_supporter_to_hand(card_id, info, obs)
        if data and data.cardType == CardType.STADIUM:
            return 10000
        return score_to_hand_generic(card_id, info, obs)

    return score_to_hand_generic(card_id, info, obs)


def score_poke_pad_to_hand(card_id: int, info: BoardInfo, obs: Observation) -> int:
    bench_open = can_play_more_bench(obs, info)
    snorunt_access = snorunt_access_count(info)
    froslass_line_access = froslass_line_access_count(info)
    normal_froslass_access = normal_froslass_access_count(info)
    bronzor_access = bronzor_access_count(info)
    bronzong_access = bronzong_access_count(info)
    bronzong_line_access = bronzong_line_access_count(info)
    munkidori_access = munkidori_access_count(info)

    if card_id == SNORUNT:
        if not bench_open and info.field_counts[SNORUNT] == 0:
            return 9000
        if froslass_line_access == 0:
            return 39000
        if froslass_line_access < FROSLASS_LINE_TARGET:
            return 34200 - froslass_line_access * 1200
        return 4200

    if card_id == MUNKIDORI:
        if not bench_open and info.field_counts[MUNKIDORI] == 0:
            return 9000
        if munkidori_access == 0:
            return 37000
        if munkidori_access < MUNKIDORI_TARGET:
            return 33000 - munkidori_access * 1200
        if wants_munkidori_from_search(info):
            return 18400
        return 3800

    if card_id == BRONZOR:
        if not bench_open and info.field_counts[BRONZOR] == 0:
            return 8200
        if bronzong_line_access == 0:
            return 36000
        if bronzong_line_access < BRONZONG_TARGET:
            return 28600
        return 3600

    if card_id == FROSLASS:
        if normal_froslass_access >= NORMAL_FROSLASS_TARGET:
            return 7200
        if snorunt_access == 0:
            return 7600
        if info.field_counts[SNORUNT] > 0:
            if normal_froslass_access == 0:
                return 35500
            return 30800
        return 29200 if normal_froslass_access == 0 else 24600

    if card_id == BRONZONG:
        if bronzong_access >= BRONZONG_TARGET:
            return 6500
        if info.field_counts[BRONZOR] > 0:
            return 33200
        if bronzor_access > 0:
            return 27600
        return 7000

    return -800


def score_supporter_to_hand(card_id: int, info: BoardInfo, obs: Observation) -> int:
    if card_id == SALVATORE:
        if wants_bronzong(info):
            return 34800
        if wants_mega_froslass(info):
            return 33600
        return 12000
    if card_id == HILDA:
        if wants_normal_froslass(info):
            return 33400
        return 31400 if key_evolution_needed(info) or key_energy_needed(info) else 12000
    if card_id == CRISPIN:
        if any(p.id == MUNKIDORI and not has_dark(p) for p in info.my_field):
            return 31800
        return 30200 if key_energy_needed(info) else 9000
    if card_id == BROCKS_SCOUTING:
        return (
            27600
            if wants_snorunt(info) or wants_bronzor(info) or wants_munkidori(info)
            else 11000 if key_evolution_needed(info) else 9500
        )
    if card_id == LILLIES_DETERMINATION:
        hand_count = obs.current.players[info.my_index].handCount
        return 24800 if hand_count <= 3 else 8200
    if card_id == LANAS_AID:
        recoverable = sum(
            info.discard_counts[cid] for cid in NON_RULE_BOX_POKEMON | BASIC_ENERGY
        )
        if info.discard_counts[FROSLASS] and wants_normal_froslass(info):
            return 28600
        if info.discard_counts[MUNKIDORI] and wants_munkidori(info):
            return 27600
        return 19800 if recoverable >= 2 else 6200
    if card_id == BOSSS_ORDERS:
        return 16000 if opponent_has_bench(info, obs) else 3000
    return -700


def score_energy_to_hand(card_id: int, info: BoardInfo) -> int:
    if card_id == BASIC_DARK:
        return (
            34000
            if any(p.id == MUNKIDORI and not has_dark(p) for p in info.my_field)
            else 9200
        )
    if card_id == BASIC_WATER:
        return (
            30600
            if any(
                p.id in {SNORUNT, FROSLASS, MEGA_FROSLASS_EX} and not has_water(p)
                for p in info.my_field
            )
            else 8600
        )
    if card_id in {BASIC_PSYCHIC, TELEPATH_PSYCHIC}:
        if any(p.id == BRONZONG and not has_psychic(p) for p in info.my_field):
            return 27600
        if any(p.id == MUNKIDORI and not has_psychic(p) for p in info.my_field):
            return 10400
        return 7200
    return -500


def score_to_hand_generic(card_id: int, info: BoardInfo, obs: Observation) -> int:
    if card_id in EVOLUTIONS:
        return evolution_priority(card_id, info)
    if card_id in BASIC_POKEMON:
        return setup_priority(card_id, info)
    if card_id in ENERGY_CARDS:
        return score_energy_to_hand(card_id, info)
    if card_id in SUPPORTERS:
        return score_supporter_to_hand(card_id, info, obs)
    if card_id == NIGHT_STRETCHER:
        return 9000
    if card_id in {ULTRA_BALL, POKE_PAD, BUDDY_BUDDY_POFFIN}:
        return 8000
    if card_id == AIR_BALLOON:
        return 4200
    return 1000


def own_card_keep_value(card_id: int, info: BoardInfo, obs: Observation) -> int:
    if card_id == FROSLASS:
        if info.field_counts[FROSLASS] == 0:
            return 28500
        return 21800 if info.field_counts[FROSLASS] < NORMAL_FROSLASS_TARGET else 7600
    if card_id == MEGA_FROSLASS_EX:
        return 25000 if info.field_counts[MEGA_FROSLASS_EX] == 0 else 9000
    if card_id == BRONZONG:
        return 23500 if info.field_counts[BRONZONG] == 0 else 7600
    if card_id == MUNKIDORI:
        return 20500 if wants_munkidori(info) else 7600
    if card_id == SNORUNT:
        return 17800 if wants_snorunt(info) else 5200
    if card_id == BRONZOR:
        return 16400 if wants_bronzor(info) else 4700
    if card_id in ENERGY_CARDS:
        return 13800 if key_energy_needed(info) else 3800
    if card_id == LANAS_AID:
        return 10400
    if card_id in SUPPORTERS:
        return 9200
    if card_id in ITEMS:
        return 6200
    if card_id == AIR_BALLOON:
        return 3600
    return 1000


def score_discard_card(
    card: Pokemon | Card | None, option: Option, info: BoardInfo, obs: Observation
) -> int:
    if card is None:
        return -1000
    if option.playerIndex == info.op_index:
        data = card_data(card.id)
        score = 3000
        if data and data.cardType == CardType.ITEM:
            score += 2200
        if data and data.cardType == CardType.SUPPORTER:
            score += 1400
        if card.id in ENERGY_CARDS:
            score += 1000
        return score
    duplicates = max(0, info.hand_counts[card.id] - 1)
    return 10000 - own_card_keep_value(card.id, info, obs) + duplicates * 1600


def score_bench_card(
    card: Pokemon | Card | None, info: BoardInfo, obs: Observation
) -> int:
    if card is None:
        return -1000
    if card.id == MEOWTH_EX:
        if obs.select and obs.select.context == SelectContext.SETUP_BENCH_POKEMON:
            return -2500
        return 26000 if support_search_needed(info, obs) else -2500
    if card.id == BRONZOR:
        if wants_bronzor(info):
            return 25600
        return 17000 if active_bronzor_needs_backup(info, obs) else -1400
    if card.id in BASIC_POKEMON:
        base = setup_priority(card.id, info)
        return base + 18000 if base > 0 else base
    return -500


def score_damage_counter_target(
    card: Pokemon | Card | None, option: Option, info: BoardInfo, obs: Observation
) -> int:
    effect_id = obs.select.effect.id if obs.select and obs.select.effect else 0
    if not isinstance(card, Pokemon):
        return -1000
    if effect_id == MUNKIDORI:
        if option.playerIndex == info.my_index:
            dmg = damage_on(card)
            if dmg <= 0:
                return -5000
            if card.id == MUNKIDORI and card.hp <= 30:
                return dmg * 50
            return (
                30000
                + min(dmg, 30) * 50
                + (1200 if card.id in {MUNKIDORI, MEOWTH_EX} else 0)
            )
        if option.playerIndex == info.op_index:
            score = 30000 + max(0, 40 - card.hp) * 180
            if option.area == AreaType.ACTIVE:
                score += 2200
            if card.hp <= 30:
                score += 6000
            return score
    if option.playerIndex == info.op_index:
        return 5000 + max(0, 120 - card.hp)
    if option.playerIndex == info.my_index:
        return -5000 - card.hp
    return 0


def score_number(option: Option, info: BoardInfo, obs: Observation) -> int:
    number = option.number or 0
    context = obs.select.context
    if context in {
        SelectContext.DAMAGE_COUNTER_COUNT,
        SelectContext.REMOVE_DAMAGE_COUNTER_COUNT,
    }:
        return number * 1000
    if context == SelectContext.DRAW_COUNT:
        my_deck_count = obs.current.players[info.my_index].deckCount
        return -number * 1000 if my_deck_count <= number + 2 else number * 120
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
        return 900 if yes else -100
    return 100 if yes else 0


def score_option(index: int, option: Option, info: BoardInfo, obs: Observation) -> int:
    context = obs.select.context
    card = get_card(obs, option.area, option.index, option.playerIndex)

    if option.type == OptionType.NUMBER:
        return score_number(option, info, obs)
    if option.type in {OptionType.YES, OptionType.NO}:
        return score_yes_no(option, info, obs)
    if option.type == OptionType.PLAY:
        hand_card = get_card(obs, AreaType.HAND, option.index, info.my_index)
        return (
            score_play_card(hand_card.id, info, obs)
            if isinstance(hand_card, Card)
            else -1000
        )
    if option.type == OptionType.EVOLVE:
        return score_evolve_option(option, info, obs)
    if option.type == OptionType.ATTACH:
        return score_attach_option(option, info, obs)
    if option.type == OptionType.ABILITY:
        return score_ability_option(option, info, obs)
    if option.type == OptionType.ATTACK:
        return score_attack(option, info, obs)
    if option.type in {
        OptionType.CARD,
        OptionType.TOOL_CARD,
        OptionType.ENERGY_CARD,
        OptionType.ENERGY,
    }:
        if context in {
            SelectContext.SETUP_ACTIVE_POKEMON,
            SelectContext.TO_ACTIVE,
            SelectContext.SWITCH,
        }:
            if option.playerIndex == info.op_index:
                return score_opponent_switch_target(card, option, info)
            return score_switch_to_active(card, info)
        if context in {
            SelectContext.SETUP_BENCH_POKEMON,
            SelectContext.TO_BENCH,
            SelectContext.TO_FIELD,
        }:
            return score_bench_card(card, info, obs)
        if context == SelectContext.TO_HAND:
            return score_to_hand(card, info, obs)
        if context in {
            SelectContext.DISCARD,
            SelectContext.DISCARD_CARD_OR_ATTACHED_CARD,
            SelectContext.NOT_MOVE,
        }:
            return score_discard_card(card, option, info, obs)
        if context in {SelectContext.TO_DECK, SelectContext.TO_DECK_BOTTOM}:
            return -own_card_keep_value(card.id, info, obs) if card else 0
        if context in {
            SelectContext.DAMAGE_COUNTER,
            SelectContext.DAMAGE_COUNTER_ANY,
            SelectContext.DAMAGE,
        }:
            return score_damage_counter_target(card, option, info, obs)
        if context in {SelectContext.HEAL, SelectContext.REMOVE_DAMAGE_COUNTER}:
            return (
                damage_on(card)
                if isinstance(card, Pokemon) and option.playerIndex == info.my_index
                else -1000
            )
        if context in {SelectContext.ATTACH_TO, SelectContext.ATTACH_FROM}:
            if isinstance(card, Pokemon):
                return score_attach_target(card, info)
            if isinstance(card, Card):
                return score_energy_to_hand(card.id, info)
        return score_to_hand(card, info, obs)
    if option.type == OptionType.DISCARD:
        return -500
    if option.type == OptionType.RETREAT:
        if info.my_active and info.my_active.id not in {MEGA_FROSLASS_EX, BRONZONG}:
            return (
                9000
                if any(
                    score_switch_to_active(p, info) > 15000
                    for p in obs.current.players[info.my_index].bench
                )
                else -300
            )
        return -500
    if option.type == OptionType.END:
        return 0
    return 0


def score_attach_target(target: Pokemon, info: BoardInfo) -> int:
    if target.id == MUNKIDORI:
        return 26000 if not has_dark(target) else 9000
    if target.id == MEGA_FROSLASS_EX:
        return 24000 if not has_water(target) else 9000
    if target.id == BRONZONG:
        return 22000 if not has_psychic(target) else 5000
    if target.id in {SNORUNT, FROSLASS}:
        return 16000 if not has_water(target) else 3000
    return 0


def score_opponent_switch_target(
    card: Pokemon | Card | None, option: Option, info: BoardInfo
) -> int:
    if not isinstance(card, Pokemon):
        return -1000
    score = 1000 + max(0, 120 - card.hp) * 30
    if card.hp <= 60:
        score += 4000
    if card_data(card.id) and not card_data(card.id).basic:
        score += 1200
    if is_rule_box(card):
        score += 900
    return score


def choose_by_scores(obs: Observation, scores: list[int]) -> list[int]:
    select = obs.select
    if select.maxCount == 0 or not select.option:
        return []
    ranked = sorted(range(len(scores)), key=lambda i: (scores[i], -i), reverse=True)

    if select.context == SelectContext.MAIN:
        return [ranked[0]]

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
    return choose_by_scores(obs, scores)
