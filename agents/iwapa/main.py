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
    PlayerState,
    SelectContext,
    all_attack,
    all_card_data,
    to_observation_class,
)

"""
Iwaparesu (Crustle) Control Deck
This deck uses Iwaparesu (Crustle) and Ougapon Ishizue to lock down opponent's ex/ability Pokemon,
while using Mashimashira's Adrena-Brain to move damage counters to the opponent's board.
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

# Decklist Card IDs
Sheimi = 343
Ishizumai = 344
Iwaparesu = 345
Kodack = 858
Mashimashira = 112
Kichikigisu = 970
Ougapon_Ishizue = 117
Basic_Grass_Energy = 1
Grow_Grass_Energy = 18
Basic_Psychic_Energy = 5
Basic_Fighting_Energy = 6
Basic_Darkness_Energy = 7
Mist_Energy = 11
Buddy_Buddy_Poffin = 1086
Night_Stretcher = 1097
Ultra_Ball = 1121
Pokegear_3_0 = 1122
Pokepad = 1152
Hero_Cape = 1159
Boss_Orders = 1182
Suiren_Care = 1184
Matsuba_Conviction = 1187
Xerosic_Scheme = 1197
Acamatsu = 1198
Rockets_Lambda = 1219
Lillies_Determination = 1227

SUPPORTER_IDS = {
    Boss_Orders,
    Suiren_Care,
    Matsuba_Conviction,
    Xerosic_Scheme,
    Acamatsu,
    Rockets_Lambda,
    Lillies_Determination,
}


@dataclass
class BattlePlan:
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


def is_ex_pokemon(pokemon_id: int) -> bool:
    data = card_table.get(pokemon_id)
    if data is None:
        return False
    return data.ex or data.megaEx


def has_ability(pokemon_id: int) -> bool:
    data = card_table.get(pokemon_id)
    if data is None:
        return False
    return len(data.skills) > 0


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
    score += pokemon.hp
    return score


def detect_opponent_features(
    obs: Observation, op_state: PlayerState
) -> tuple[bool, bool, bool]:
    """Scan opponent's visible cards and evolutionary lines to detect features.

    Returns (is_ex, has_ability, has_bomb).
    """
    is_ex = False
    has_ability_flag = False
    has_bomb_flag = False

    # 1. Collect all visible opponent card IDs
    cards_to_check: list[int] = []
    for p in op_state.active + op_state.bench:
        if p is not None:
            cards_to_check.append(p.id)
    for c in op_state.discard:
        if c is not None:
            cards_to_check.append(c.id)

    # 2. Collect card IDs from logs
    for log in obs.logs:
        ids = [
            log.cardId,
            log.cardIdActive,
            log.cardIdBench,
            log.cardIdBefore,
            log.cardIdAfter,
            log.cardIdTarget,
        ]
        for cid in ids:
            if cid is not None and cid > 0:
                cards_to_check.append(cid)

    unique_cids = set(cards_to_check)
    names_to_check: set[str] = set()

    # 3. Check characteristics of current cards
    for cid in unique_cids:
        card = card_table.get(cid)
        if card is not None:
            names_to_check.add(card.name)
            if card.ex or card.megaEx:
                is_ex = True
            if len(card.skills) > 0:
                has_ability_flag = True
            if cid in {131, 132, 133}:  # Duskull line
                has_bomb_flag = True

    # 4. Check future evolution forms from the database
    for card in all_card:
        if card.evolvesFrom in names_to_check:
            if card.ex or card.megaEx:
                is_ex = True
            if len(card.skills) > 0:
                has_ability_flag = True
            if card.cardId in {132, 133}:
                has_bomb_flag = True

    return is_ex, has_ability_flag, has_bomb_flag


def _build_battle_plan(
    state,
    my_state,
    op_state,
    hand_counts: dict[int, int],
    priority_attacker_id: int,
) -> BattlePlan:
    current_plan = BattlePlan()
    opponent_active = op_state.active[0] if len(op_state.active) > 0 else None
    if opponent_active is None:
        return current_plan

    active = my_state.active[0] if len(my_state.active) > 0 else None

    if active is not None and active.id != priority_attacker_id:
        # 1. Look for preferred evolution on bench
        for index, pokemon in enumerate(my_state.bench):
            if pokemon.id == priority_attacker_id:
                current_plan.switch_target_index = index
                break
        # 2. Look for alternative evolution on bench
        if current_plan.switch_target_index == -1:
            for index, pokemon in enumerate(my_state.bench):
                if pokemon.id in {Iwaparesu, Ougapon_Ishizue}:
                    current_plan.switch_target_index = index
                    break
        # 3. Look for Ishizumai ONLY if it is ready to use Kakusei immediately
        # (Must have energy attached, or we have grass energy in hand and can attach it this turn)
        if current_plan.switch_target_index == -1:
            for index, pokemon in enumerate(my_state.bench):
                if pokemon.id == Ishizumai:
                    has_energy = len(pokemon.energies) >= 1
                    can_attach = (not state.energyAttached) and (
                        hand_counts[Basic_Grass_Energy] > 0
                        or hand_counts[Grow_Grass_Energy] > 0
                    )
                    if has_energy or can_attach:
                        current_plan.switch_target_index = index
                        break

    return current_plan


def _has_supporter_in_hand(hand_counts: dict[int, int]) -> bool:
    return any(hand_counts[card_id] > 0 for card_id in SUPPORTER_IDS)


def _energy_attach_score(
    pokemon: Pokemon,
    energy_card: Card,
    active_zone: bool,
    state,
    my_state,
    hand_counts: dict[int, int],
    priority_attacker_id: int,
    field_counts: dict[int, int],
) -> int:
    energy_count = len(pokemon.energies)
    score = 0

    is_grass_card = energy_card.id in {Basic_Grass_Energy, Grow_Grass_Energy}
    is_fighting_card = energy_card.id == Basic_Fighting_Energy

    # Check if Dwebble/Crustle on our field has any Grass energy attached
    crustle_has_grass = False
    for p in my_state.active + my_state.bench:
        if p is not None and p.id in {Ishizumai, Iwaparesu}:
            if any(
                e == EnergyType.GRASS or e == EnergyType.RAINBOW for e in p.energies
            ):
                crustle_has_grass = True
                break

    if pokemon.id == Mashimashira:
        # Mashimashira needs basic Darkness energy to activate Adrena-Brain.
        has_dark = any(
            e == EnergyType.DARKNESS or e == EnergyType.RAINBOW
            for e in pokemon.energies
        )
        if energy_card.id == Basic_Darkness_Energy:
            if not has_dark:
                score = 25000  # Extremely high priority
            else:
                score = 5000
        else:
            if is_grass_card:
                score = 50  # Never waste grass energy on bench sitters
            else:
                score = 100  # Deprioritized fallback

    elif pokemon.id == Kichikigisu:
        has_dark = any(
            e == EnergyType.DARKNESS or e == EnergyType.RAINBOW
            for e in pokemon.energies
        )
        if energy_card.id == Basic_Darkness_Energy:
            if not has_dark:
                score = 18000
            else:
                score = 4000
        else:
            if is_grass_card:
                score = 50  # Never waste grass energy
            else:
                score = 100

    elif pokemon.id == Iwaparesu:
        has_grass = any(
            e == EnergyType.GRASS or e == EnergyType.RAINBOW for e in pokemon.energies
        )

        if not has_grass:
            if is_grass_card:
                # Max priority if Crustle is our target attacker
                score = 26000 if priority_attacker_id == Iwaparesu else 15000
            else:
                score = 100
        else:
            if is_grass_card:
                score = 18000 if energy_count < 3 else 3000
            elif energy_card.id == Mist_Energy:
                score = 20000 if energy_count < 3 else 2500
            else:
                score = 1000 if energy_count < 3 else 200

    elif pokemon.id == Ougapon_Ishizue:
        has_fighting = any(
            e == EnergyType.FIGHTING or e == EnergyType.RAINBOW
            for e in pokemon.energies
        )

        if not has_fighting:
            if is_fighting_card:
                score = 26000 if priority_attacker_id == Ougapon_Ishizue else 15000
            else:
                score = 100
        else:
            if is_fighting_card:
                score = 17000 if energy_count < 3 else 3000
            elif energy_card.id == Mist_Energy:
                score = 19000 if energy_count < 3 else 2500
            elif is_grass_card:
                # Grass energy is extremely scarce. Only attach to Ogerpon if Crustle
                # already has grass energy secured. Otherwise preserve for Crustle/Dwebble.
                if crustle_has_grass:
                    score = 6000 if energy_count < 3 else 200
                else:
                    score = 50  # Safely preserve grass energy in hand
            else:
                score = 1000 if energy_count < 3 else 200

    elif pokemon.id == Ishizumai:
        if is_grass_card:
            score = 22000 if priority_attacker_id == Iwaparesu else 12000
        else:
            score = 50
    else:
        score = 100

    if active_zone:
        score += 1000

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
    is_op_has_bomb: bool,
) -> int:
    score = 1000

    if card.id == Buddy_Buddy_Poffin:
        if bench_room and (
            field_counts[Ishizumai] + field_counts[Iwaparesu] < 2
            or field_counts[Mashimashira] < 2
        ):
            score = 26000
        else:
            score = 50

    elif card.id == Ultra_Ball:
        if my_state.handCount >= 3:
            if (
                field_counts[Ishizumai] >= 1
                and field_counts[Iwaparesu] == 0
                and hand_counts[Iwaparesu] == 0
            ):
                score = 24000
            elif (
                field_counts[Ougapon_Ishizue] == 0 and hand_counts[Ougapon_Ishizue] == 0
            ):
                score = 20000
            else:
                score = 3000
        else:
            score = 50

    elif card.id == Pokepad:
        if (
            field_counts[Mashimashira] + hand_counts[Mashimashira] < 2
            or field_counts[Iwaparesu] + hand_counts[Iwaparesu] < 1
        ):
            score = 23000
        else:
            score = 7000

    elif card.id == Night_Stretcher:
        if (
            discard_counts[Iwaparesu] > 0
            or discard_counts[Mashimashira] > 0
            or discard_counts[Basic_Darkness_Energy] > 0
        ):
            score = 15000
        else:
            score = 2000

    elif card.id == Pokegear_3_0:
        if not _has_supporter_in_hand(hand_counts):
            score = 16000
        else:
            score = 3000

    elif card.id == Hero_Cape:
        if field_counts[Iwaparesu] >= 1 or field_counts[Ougapon_Ishizue] >= 1:
            score = 22000
        else:
            score = 50

    elif card.id == Boss_Orders:
        score = 10000

    elif card.id == Acamatsu:
        if not state.energyAttached:
            score = 23000
        else:
            score = 4000

    elif card.id == Lillies_Determination:
        if my_state.handCount <= 4:
            score = 19000
        else:
            score = 6000

    elif card.id == Matsuba_Conviction:
        if my_state.handCount <= 4:
            score = 17000
        else:
            score = 5000

    elif card.id == Suiren_Care:
        score = 8000

    elif card.id == Xerosic_Scheme:
        score = 7000

    elif card.id == Rockets_Lambda:
        score = 14000

    if card.id in SUPPORTER_IDS and state.supporterPlayed:
        score = 50

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

    field_counts: dict[int, int] = defaultdict(int)
    hand_counts: dict[int, int] = defaultdict(int)
    discard_counts: dict[int, int] = defaultdict(int)

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

    # Scan opponent's board & logs for priority setup and metadata
    is_op_ex, is_op_has_ability, is_op_has_bomb = detect_opponent_features(
        obs, op_state
    )

    if is_op_ex:
        priority_attacker_id = Iwaparesu
    elif is_op_has_ability:
        priority_attacker_id = Ougapon_Ishizue
    else:
        priority_attacker_id = Iwaparesu

    plan = _build_battle_plan(
        state, my_state, op_state, hand_counts, priority_attacker_id
    )

    scores: list[int] = []
    for option in select.option:
        score = 0

        if option.type == OptionType.NUMBER:
            score = option.number if option.number is not None else 0
        elif option.type == OptionType.YES:
            score = 1
        elif option.type == OptionType.NO:
            score = 0
        elif option.type == OptionType.CARD:
            card = get_card(obs, option.area, option.index, option.playerIndex)
            if card is not None:
                energy_count = len(card.energies) if isinstance(card, Pokemon) else 0

                if context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
                    # Smart active candidate evaluation
                    score = 1000 + energy_count * 25
                    if option.index == plan.switch_target_index:
                        score += 8000

                    if isinstance(card, Pokemon):
                        if card.id == Iwaparesu:
                            has_grass = any(
                                e == EnergyType.GRASS or e == EnergyType.RAINBOW
                                for e in card.energies
                            )
                            if len(card.energies) >= 2 and has_grass:
                                score += 6000
                            else:
                                score += 1500 + len(card.energies) * 50
                        elif card.id == Ougapon_Ishizue:
                            has_fighting = any(
                                e == EnergyType.FIGHTING or e == EnergyType.RAINBOW
                                for e in card.energies
                            )
                            if len(card.energies) >= 2 and has_fighting:
                                score += 6000
                            else:
                                score += 1500 + len(card.energies) * 50
                        elif card.id == Ishizumai:
                            # Evaluate if it can immediately evolve via Kakusei
                            has_energy = len(card.energies) >= 1
                            can_attach = (not state.energyAttached) and (
                                hand_counts[Basic_Grass_Energy] > 0
                                or hand_counts[Grow_Grass_Energy] > 0
                            )
                            if has_energy or can_attach:
                                score += 4000
                            else:
                                score += 100  # Poor active target, keep behind wall
                        elif card.id == Kichikigisu:
                            # Fezandipiti is a great wall if it has Darkness energy (50% immune)
                            has_dark = any(
                                e == EnergyType.DARKNESS or e == EnergyType.RAINBOW
                                for e in card.energies
                            )
                            if has_dark:
                                score += 3000
                            else:
                                score += 1000
                        elif card.id == Mashimashira:
                            score += 800
                        elif card.id == Sheimi:
                            score += 300
                        elif card.id == Kodack:
                            score += 200

                elif context in {
                    SelectContext.SETUP_ACTIVE_POKEMON,
                    SelectContext.TO_FIELD,
                }:
                    # Setup active selection
                    if priority_attacker_id == Iwaparesu:
                        if card.id == Ishizumai:
                            score = 5000
                        elif card.id == Ougapon_Ishizue:
                            score = 3000
                        else:
                            score = 100
                    else:
                        if card.id == Ougapon_Ishizue:
                            score = 5000
                        elif card.id == Ishizumai:
                            score = 3000
                        else:
                            score = 100
                elif context in {
                    SelectContext.SETUP_BENCH_POKEMON,
                    SelectContext.TO_BENCH,
                }:
                    if card.id == Ishizumai:
                        score = 6000 if bench_room else 50
                    elif card.id == Mashimashira:
                        score = 5500 if bench_room else 50
                    elif card.id == Sheimi:
                        score = 5000 if field_counts[Sheimi] == 0 else 50
                    elif card.id == Kodack:
                        # Only bench Psyduck if opponent has Dusknoir/自爆 line
                        score = (
                            4500
                            if (
                                is_op_has_bomb
                                and field_counts[Kodack] == 0
                                and bench_room
                            )
                            else 50
                        )
                    elif card.id == Kichikigisu:
                        # Only keep max 1 Fezandipiti to prevent bench clogging
                        score = (
                            4000
                            if (field_counts[Kichikigisu] == 0 and bench_room)
                            else 50
                        )
                    elif card.id == Ougapon_Ishizue:
                        score = 3000
                elif context == SelectContext.TO_HAND:
                    score = 100
                    if card.id == Iwaparesu:
                        if (
                            field_counts[Ishizumai] >= 1
                            and field_counts[Iwaparesu] == 0
                        ):
                            score = 1800
                        else:
                            score = 1200 - field_counts[Iwaparesu] * 100
                    elif card.id == Ishizumai:
                        score = 1000 - field_counts[Ishizumai] * 150
                    elif card.id == Mashimashira:
                        score = 1500 if field_counts[Mashimashira] < 2 else 900
                    elif card.id in {
                        Basic_Darkness_Energy,
                        Basic_Grass_Energy,
                    }:
                        score = 800
                    elif card.id == Sheimi:
                        score = 1100 if field_counts[Sheimi] == 0 else 100
                    elif card.id == Kodack:
                        score = (
                            1050
                            if (is_op_has_bomb and field_counts[Kodack] == 0)
                            else 100
                        )
                elif context in {
                    SelectContext.DAMAGE,
                    SelectContext.EFFECT_TARGET,
                }:
                    score = pokemon_score(card) if isinstance(card, Pokemon) else 0
                elif context in {
                    SelectContext.DAMAGE_COUNTER,
                    SelectContext.DAMAGE_COUNTER_ANY,
                }:
                    # Adrena-Brain logic
                    if isinstance(card, Pokemon):
                        if option.playerIndex == my_index:
                            damage = card.maxHp - card.hp
                            score = 5000 + damage * 100
                        else:
                            if card.hp <= 30:
                                score = 30000
                            else:
                                score = 10000 + pokemon_score(card)
                elif context == SelectContext.HEAL:
                    if card.id == Iwaparesu and card.hp < card.maxHp:
                        score = 10000 - card.hp
                elif context == SelectContext.DISCARD:
                    score = -500
                    if card.id in SUPPORTER_IDS:
                        score = 100
                        if hand_counts[card.id] >= 2:
                            score += 300
                    elif card.id == Pokegear_3_0:
                        score = 80
                    elif card.id == Ishizumai and field_counts[Ishizumai] >= 2:
                        score = 200
                elif context in {
                    SelectContext.ATTACH_TO,
                    SelectContext.ATTACH_FROM,
                }:
                    energy_card = select.contextCard
                    if energy_card is not None and isinstance(card, Pokemon):
                        score = _energy_attach_score(
                            card,
                            energy_card,
                            option.area == AreaType.ACTIVE,
                            state,
                            my_state,
                            hand_counts,
                            priority_attacker_id,
                            field_counts,
                        )
                    else:
                        if card.id == Iwaparesu:
                            score = 15000 if len(card.energies) < 3 else 1000
                        elif card.id == Ougapon_Ishizue:
                            score = 14000 if len(card.energies) < 3 else 1000
                        elif card.id == Mashimashira:
                            has_dark = any(
                                e == EnergyType.DARKNESS for e in card.energies
                            )
                            score = 12000 if not has_dark else 800
                        else:
                            score = 100

        elif option.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            if card is not None:
                data = card_table[card.id]
                if data.cardType == CardType.POKEMON:
                    if card.id == Ishizumai:
                        score = 25000 - field_counts[Ishizumai] * 1000
                    elif card.id == Mashimashira:
                        score = 24000 - field_counts[Mashimashira] * 1000
                    elif card.id == Sheimi:
                        score = 23000 if field_counts[Sheimi] == 0 else 50
                    elif card.id == Kodack:
                        score = (
                            22000
                            if (is_op_has_bomb and field_counts[Kodack] == 0)
                            else 50
                        )
                    elif card.id == Ougapon_Ishizue:
                        score = 21000 if field_counts[Ougapon_Ishizue] == 0 else 5000
                    elif card.id == Kichikigisu:
                        score = (
                            20000 - field_counts[Kichikigisu] * 15000
                        )  # Max 1 Fezandipiti
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
                        is_op_has_bomb,
                    )

        elif option.type == OptionType.ATTACH:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            pokemon = get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
            if card is not None and isinstance(pokemon, Pokemon):
                if card.id == Hero_Cape:
                    if pokemon.id == Iwaparesu:
                        score = 28000
                    elif pokemon.id == Ougapon_Ishizue:
                        score = 25000
                    else:
                        score = 50
                else:
                    score = _energy_attach_score(
                        pokemon,
                        card,
                        option.inPlayArea == AreaType.ACTIVE,
                        state,
                        my_state,
                        hand_counts,
                        priority_attacker_id,
                        field_counts,
                    )

        elif option.type == OptionType.EVOLVE:
            card = get_card(obs, AreaType.HAND, option.index, my_index)
            pokemon = get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
            if card is not None and pokemon is not None:
                if card.id == Iwaparesu and pokemon.id == Ishizumai:
                    score = 30000 + len(pokemon.energies) * 100
                else:
                    score = 50

        elif option.type == OptionType.ABILITY:
            ability_pokemon = get_card(obs, option.area, option.index, my_index)
            if ability_pokemon is not None and ability_pokemon.id == Mashimashira:
                has_damage = False
                for p in my_state.active + my_state.bench:
                    if p is not None and p.hp < p.maxHp:
                        has_damage = True
                        break
                if has_damage:
                    score = 30000
                else:
                    score = 50
            else:
                score = 50

        elif option.type == OptionType.RETREAT:
            active = my_state.active[0] if len(my_state.active) > 0 else None
            if active is not None:
                if active.id in {
                    Ishizumai,
                    Kodack,
                    Sheimi,
                    Mashimashira,
                    Kichikigisu,
                }:
                    # Low score if no target prepared, allowing END (200) to override retreat.
                    score = 15000 if plan.switch_target_index >= 0 else 50
                elif active.id == Ougapon_Ishizue:
                    score = 15000 if plan.switch_target_index >= 0 else 50
                elif active.id == Iwaparesu:
                    score = 2000 if plan.switch_target_index >= 0 else 50
                else:
                    score = 50

        elif option.type == OptionType.ATTACK:
            active = my_state.active[0] if len(my_state.active) > 0 else None
            if active is not None:
                if active.id == Iwaparesu:
                    score = 30000
                elif active.id == Ougapon_Ishizue:
                    score = 29000
                elif active.id == Ishizumai:
                    score = 28000
                elif active.id == Mashimashira:
                    score = 15000
                elif active.id == Kichikigisu:
                    score = 18000
                else:
                    score = 1000

        elif option.type == OptionType.END:
            score = 200

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
