import os
from collections import defaultdict
from dataclasses import dataclass

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
Mega Starmie ex Deck
This deck prioritizes establishing Mega Starmie ex and attacking with Jetting Blow.
If Jetting Blow cannot take the knockout but Nebula Beam can do so with
Ignition Energy, the agent prefers Nebula Beam. Otherwise it defaults to
Jetting Blow.
"""


def _load_deck() -> list[int]:
    file_path = "deck.csv"
    if not os.path.exists(file_path):
        file_path = "/kaggle_simulations/agent/" + file_path
    with open(file_path, "r", encoding="utf-8") as file:
        return [int(line) for line in file.read().splitlines() if line.strip()]


my_deck = _load_deck()

all_card = all_card_data()
card_table = {card.cardId: card for card in all_card}
attack_table = {attack.attackId: attack for attack in all_attack()}


# Decklist
Staryu = 1030  # ×4
Mega_Starmie_ex = 1031  # ×4
Basic_Water_Energy = 3  # ×4
Ignition_Energy = 17  # ×4
Buddy_Buddy_Poffin = 1086  # ×4
Scoop_Up_Cyclone = 1093  # ×1
Night_Stretcher = 1097  # ×2
Crushing_Hammer = 1120  # ×4
Ultra_Ball = 1121  # ×3
Pokegear_3_0 = 1122  # ×4
Mega_Signal = 1145  # ×1
Salvatore = 1189  # ×4
Team_Rockets_Petrel = 1219  # ×4
Hilda = 1225  # ×4
Lillies_Determination = 1227  # ×4
Wallys_Compassion = 1229  # ×4

SUPPORTER_IDS = {
    Team_Rockets_Petrel,
    Hilda,
    Lillies_Determination,
    Wallys_Compassion,
    Salvatore,
}


def _pick_attack_id(card_id: int, damage: int) -> int:
    card = card_table[card_id]
    for attack_id in card.attacks:
        if attack_table[attack_id].damage == damage:
            return attack_id
    return card.attacks[0]


STARMIE_UPPER_ATTACK_ID = _pick_attack_id(Mega_Starmie_ex, 120)
STARMIE_LOWER_ATTACK_ID = _pick_attack_id(Mega_Starmie_ex, 210)


@dataclass
class BattlePlan:
    preferred_attack_id: int = -1
    use_lower_attack: bool = False
    switch_target_index: int = -1


plan = BattlePlan()
pre_turn = -1


def get_card(
    obs: Observation,
    area: AreaType,
    index: int,
    player_index: int,
) -> Pokemon | Card | None:
    """Safely extract a Card or Pokemon object from a zone."""
    ps = obs.current.players[player_index]
    match area:
        case AreaType.DECK:
            return obs.select.deck[index]
        case AreaType.HAND:
            return ps.hand[index]
        case AreaType.DISCARD:
            return ps.discard[index]
        case AreaType.ACTIVE:
            return ps.active[index]
        case AreaType.BENCH:
            return ps.bench[index]
        case AreaType.PRIZE:
            return ps.prize[index]
        case AreaType.STADIUM:
            return obs.current.stadium[index]
        case AreaType.LOOKING:
            return obs.current.looking[index]
        case _:
            return None


def prize_count(pokemon: Pokemon) -> int:
    """Return the number of Prize cards this Pokémon would yield if Knocked Out."""
    data = card_table[pokemon.id]
    count = 3 if data.megaEx else 2 if data.ex else 1
    return max(0, count)


def pokemon_score(pokemon: Pokemon) -> int:
    """Heuristic value for targeting a Pokémon with disruption or damage."""
    data = card_table[pokemon.id]
    score = prize_count(pokemon) * 1000
    score += len(pokemon.energies) * 150
    score += len(pokemon.tools) * 100
    if data.stage2:
        score += 250
    elif data.stage1:
        score += 130

    if pokemon.id in {144, 322, 323, 337}:
        score -= 200
    if pokemon.id == 112 and len(pokemon.energies) >= 1:
        score += 300
    score += pokemon.hp
    return score


def _effective_damage(attack_id: int, target: Pokemon) -> int:
    attack = attack_table[attack_id]
    damage = attack.damage
    target_data = card_table[target.id]
    if attack_id == STARMIE_UPPER_ATTACK_ID:
        if target_data.weakness == EnergyType.WATER:
            damage *= 2
        elif target_data.resistance == EnergyType.WATER:
            damage -= 30
    return max(0, damage)


def _has_supporter_in_hand(hand_counts: dict[int, int]) -> bool:
    return any(hand_counts[card_id] > 0 for card_id in SUPPORTER_IDS)


def _build_attack_plan(
    state,
    my_state,
    op_state,
    select,
    hand_counts: dict[int, int],
) -> BattlePlan:
    current_plan = BattlePlan()

    active = my_state.active[0] if len(my_state.active) > 0 else None
    opponent_active = op_state.active[0] if len(op_state.active) > 0 else None
    if active is None or opponent_active is None:
        return current_plan

    option_attack_ids = {
        option.attackId
        for option in select.option
        if option.type == OptionType.ATTACK and option.attackId is not None
    }

    if active.id == Mega_Starmie_ex:
        upper_damage = _effective_damage(STARMIE_UPPER_ATTACK_ID, opponent_active)
        lower_damage = _effective_damage(STARMIE_LOWER_ATTACK_ID, opponent_active)
        can_reach_lower = len(active.energies) >= 3 or (
            len(active.energies) == 2
            and hand_counts[Ignition_Energy] > 0
            and not state.energyAttached
        )
        upper_can_ko = upper_damage >= opponent_active.hp
        lower_can_ko = lower_damage >= opponent_active.hp

        if (
            STARMIE_UPPER_ATTACK_ID in option_attack_ids
            and STARMIE_LOWER_ATTACK_ID in option_attack_ids
        ):
            if can_reach_lower and lower_can_ko and not upper_can_ko:
                current_plan.preferred_attack_id = STARMIE_LOWER_ATTACK_ID
                current_plan.use_lower_attack = True
            else:
                current_plan.preferred_attack_id = STARMIE_UPPER_ATTACK_ID
        elif STARMIE_LOWER_ATTACK_ID in option_attack_ids:
            current_plan.preferred_attack_id = STARMIE_LOWER_ATTACK_ID
            current_plan.use_lower_attack = True
        elif STARMIE_UPPER_ATTACK_ID in option_attack_ids:
            current_plan.preferred_attack_id = STARMIE_UPPER_ATTACK_ID

        if (
            current_plan.preferred_attack_id == STARMIE_LOWER_ATTACK_ID
            and not can_reach_lower
        ):
            current_plan.preferred_attack_id = STARMIE_UPPER_ATTACK_ID
            current_plan.use_lower_attack = False

    if active.id != Mega_Starmie_ex:
        for index, pokemon in enumerate(my_state.bench):
            if pokemon.id == Mega_Starmie_ex and len(pokemon.energies) >= 1:
                current_plan.switch_target_index = index
                break

    return current_plan


def _energy_attach_score(
    pokemon: Pokemon,
    energy_card: Card,
    active_zone: bool,
    state,
    hand_counts: dict[int, int],
) -> int:
    energy_count = len(pokemon.energies)
    score = 0

    if pokemon.id == Mega_Starmie_ex:
        score = 10000
        if active_zone:
            score += 500
        if energy_card.id == Ignition_Energy:
            if energy_count == 2 and not state.energyAttached:
                score += 2500 if plan.use_lower_attack else 1800
            elif energy_count < 2:
                score += 350
            else:
                score += 1200
        elif energy_card.id == Basic_Water_Energy:
            if energy_count < 3:
                score += 1800
            else:
                score += 200
        else:
            score += 50
        if energy_count >= 3:
            score -= 1500
    elif pokemon.id == Staryu:
        score = 7000
        if energy_card.id == Basic_Water_Energy:
            score += 1200
        elif energy_card.id == Ignition_Energy:
            score += 300
        if energy_count >= 1:
            score += 100
    else:
        score = 500

    if active_zone:
        score += 50

    return score


def _play_score(
    card: Card,
    state,
    my_state,
    field_counts,
    hand_counts,
    discard_counts,
    bench_room: bool,
    stadium_id: int,
) -> int:
    score = 1000

    if card.id == Staryu:
        score = 25000
        if field_counts[Staryu] >= 2:
            score -= 1500
        if not bench_room:
            score = -1
    elif card.id == Mega_Signal:
        if (
            field_counts[Staryu] >= 1
            and field_counts[Mega_Starmie_ex] == 0
            and hand_counts[Mega_Starmie_ex] == 0
        ):
            score = 22000
        else:
            score = 1000
    elif card.id == Ultra_Ball:
        if my_state.handCount >= 3 and (
            field_counts[Staryu] == 0
            or field_counts[Mega_Starmie_ex] == 0
            or hand_counts[Ignition_Energy] == 0
        ):
            score = 20000
        else:
            score = 2500
    elif card.id == Buddy_Buddy_Poffin:
        if bench_room and field_counts[Staryu] + hand_counts[Staryu] < 2:
            score = 21000
        else:
            score = -1
    elif card.id == Hilda:
        if (
            field_counts[Staryu] >= 1
            and (
                hand_counts[Mega_Starmie_ex] == 0
                or (
                    hand_counts[Basic_Water_Energy]
                    + hand_counts[Ignition_Energy]
                    == 0
                )
            )
        ):
            score = 23000
        else:
            score = 6000
    elif card.id == Salvatore:
        if field_counts[Staryu] >= 1 and hand_counts[Mega_Starmie_ex] == 0:
            score = 21000
        else:
            score = 5000
    elif card.id == Lillies_Determination:
        if my_state.handCount <= 4:
            score = 18000
        else:
            score = 7000
    elif card.id == Pokegear_3_0:
        score = 12000 if not _has_supporter_in_hand(hand_counts) else 3500
    elif card.id == Night_Stretcher:
        if (
            discard_counts[Staryu] > 0
            or discard_counts[Basic_Water_Energy] > 0
            or discard_counts[Mega_Starmie_ex] > 0
        ):
            score = 14000
        else:
            score = 4000
    elif card.id == Team_Rockets_Petrel:
        score = 7000 if not _has_supporter_in_hand(hand_counts) else 2500
    elif card.id == Crushing_Hammer:
        score = 4000
    elif card.id == Scoop_Up_Cyclone:
        active = my_state.active[0] if len(my_state.active) > 0 else None
        if (
            active is not None
            and active.id == Mega_Starmie_ex
            and active.hp < active.maxHp
        ):
            score = 16000
        else:
            score = 2000
    elif card.id == Wallys_Compassion:
        active = my_state.active[0] if len(my_state.active) > 0 else None
        if (
            active is not None
            and active.id == Mega_Starmie_ex
            and active.hp < active.maxHp
        ):
            score = 13000
        else:
            score = 3000

    if card.id in SUPPORTER_IDS and state.supporterPlayed:
        score = -1

    if card.id == Mega_Starmie_ex:
        score = -1

    return score


def agent(obs_dict: dict) -> list[int]:
    """Main Agent Function."""
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    global plan
    global pre_turn

    if pre_turn != state.turn:
        pre_turn = state.turn
        plan = BattlePlan()

    field_counts = defaultdict(int)
    hand_counts = defaultdict(int)
    discard_counts = defaultdict(int)

    for card in my_state.active + my_state.bench:
        if card is None:
            continue
        field_counts[card.id] += 1

    for card in my_state.hand:
        hand_counts[card.id] += 1

    for card in my_state.discard:
        discard_counts[card.id] += 1

    stadium_id = state.stadium[0].id if state.stadium else 0
    bench_room = len(my_state.bench) < my_state.benchMax
    plan = _build_attack_plan(state, my_state, op_state, select, hand_counts)

    scores: list[int] = []
    for option in select.option:
        score = 0

        if option.type == OptionType.NUMBER:
            score = option.number
        elif option.type == OptionType.YES:
            score = 1
        elif option.type == OptionType.NO:
            score = 0
        elif option.type == OptionType.CARD:
            card = get_card(obs, option.area, option.index, option.playerIndex)
            if card is not None:
                energy_count = len(card.energies) if isinstance(card, Pokemon) else 0

                if context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
                    score = 1000 + energy_count * 25
                    if option.index == plan.switch_target_index:
                        score += 5000
                    if card.id == Mega_Starmie_ex:
                        score += 1200 + energy_count * 50
                    elif card.id == Staryu:
                        score += 700 + energy_count * 20
                elif context in {
                    SelectContext.SETUP_ACTIVE_POKEMON,
                    SelectContext.TO_FIELD,
                }:
                    score = 5000 if card.id == Staryu else 100
                elif context in {
                    SelectContext.SETUP_BENCH_POKEMON,
                    SelectContext.TO_BENCH,
                }:
                    if card.id == Staryu:
                        score = 6000 if bench_room else -1
                    elif card.id == Mega_Starmie_ex:
                        score = -1
                elif context == SelectContext.TO_HAND:
                    score = 100
                    if card.id == Staryu:
                        score = 1000 - field_counts[Staryu] * 150
                    elif card.id == Mega_Starmie_ex:
                        score = 1200 - field_counts[Mega_Starmie_ex] * 100
                    elif card.id == Basic_Water_Energy:
                        score = 800
                    elif card.id == Ignition_Energy:
                        score = 900 if plan.use_lower_attack else 650
                    elif card.id in SUPPORTER_IDS:
                        score = 500
                elif context in {SelectContext.DAMAGE, SelectContext.EFFECT_TARGET}:
                    if card.id == Mega_Starmie_ex and card.hp < card.maxHp:
                        score = 8000
                    elif card.id == Staryu:
                        score = 3000
                    else:
                        score = pokemon_score(card) if isinstance(card, Pokemon) else 0
                elif context == SelectContext.HEAL:
                    if card.id == Mega_Starmie_ex and card.hp < card.maxHp:
                        score = 10000 - card.hp
                    elif card.id == Staryu:
                        score = 1000
                elif context == SelectContext.DISCARD:
                    score = -500
                    if card.id in SUPPORTER_IDS:
                        score = 200
                    elif card.id == Crushing_Hammer:
                        score = 150
                    elif card.id == Pokegear_3_0:
                        score = 120
                    elif card.id == Team_Rockets_Petrel:
                        score = 100
                    elif card.id == Wallys_Compassion:
                        score = 80
                    elif card.id == Lillies_Determination:
                        score = 60
                    elif card.id == Basic_Water_Energy:
                        score = 30 if field_counts[Mega_Starmie_ex] >= 1 else 5
                    elif card.id == Ignition_Energy:
                        score = 10 if plan.use_lower_attack else -50
                    elif card.id == Staryu or card.id == Mega_Starmie_ex:
                        score = -300
                    if hand_counts[card.id] >= 2:
                        score += 300

        elif option.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            if card is not None:
                data = card_table[card.id]
                if data.cardType == CardType.POKEMON:
                    if card.id == Staryu:
                        score = 25000 - field_counts[Staryu] * 1000
                    else:
                        score = -1
                else:
                    score = _play_score(
                        card,
                        state,
                        my_state,
                        field_counts,
                        hand_counts,
                        discard_counts,
                        bench_room,
                        stadium_id,
                    )

        elif option.type == OptionType.ATTACH:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            pokemon = get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
            if card is not None and isinstance(pokemon, Pokemon):
                score = _energy_attach_score(
                    pokemon,
                    card,
                    option.inPlayArea == AreaType.ACTIVE,
                    state,
                    hand_counts,
                )
                if (
                    card.id == Ignition_Energy
                    and pokemon.id == Mega_Starmie_ex
                    and len(pokemon.energies) == 2
                    and plan.use_lower_attack
                ):
                    score += 2000
                if (
                    card.id == Basic_Water_Energy
                    and pokemon.id == Mega_Starmie_ex
                    and len(pokemon.energies) < 2
                ):
                    score += 500
                if card.id == Basic_Water_Energy and pokemon.id == Staryu:
                    score += 200

        elif option.type == OptionType.EVOLVE:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            pokemon = get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
            if card is not None and pokemon is not None:
                if card.id == Mega_Starmie_ex and pokemon.id == Staryu:
                    score = 30000 + len(pokemon.energies) * 100
                else:
                    score = -1

        elif option.type == OptionType.ABILITY:
            score = -1

        elif option.type == OptionType.RETREAT:
            active = my_state.active[0] if len(my_state.active) > 0 else None
            if active is not None and active.id == Mega_Starmie_ex:
                score = 6000 if plan.switch_target_index >= 0 else 500
            elif active is not None and active.id == Staryu:
                score = 2000 if plan.switch_target_index >= 0 else 200
            else:
                score = -1

        elif option.type == OptionType.ATTACK:
            active = my_state.active[0] if len(my_state.active) > 0 else None
            opponent_active = op_state.active[0] if len(op_state.active) > 0 else None
            if active is not None and opponent_active is not None:
                if active.id == Mega_Starmie_ex:
                    upper_damage = _effective_damage(
                        STARMIE_UPPER_ATTACK_ID,
                        opponent_active,
                    )
                    lower_damage = _effective_damage(
                        STARMIE_LOWER_ATTACK_ID,
                        opponent_active,
                    )
                    upper_can_ko = upper_damage >= opponent_active.hp
                    lower_can_ko = lower_damage >= opponent_active.hp

                    if option.attackId == STARMIE_UPPER_ATTACK_ID:
                        score = 30000
                        if upper_can_ko:
                            score += 4000
                        if plan.use_lower_attack:
                            score -= 2500
                    elif option.attackId == STARMIE_LOWER_ATTACK_ID:
                        score = 28000
                        if plan.use_lower_attack and lower_can_ko:
                            score += 7000
                        elif lower_can_ko and not upper_can_ko:
                            score += 3000
                        elif not plan.use_lower_attack:
                            score -= 4000
                    else:
                        score = 1000
                elif active.id == Staryu:
                    staryu_attack_id = card_table[Staryu].attacks[0]
                    score = 12000 if option.attackId == staryu_attack_id else 1000
                else:
                    score = 1000

        scores.append(score)

    desc_indices = [
        index
        for index, _ in sorted(
            enumerate(scores),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    return desc_indices[: select.maxCount]
