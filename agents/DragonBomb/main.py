import os
from collections import defaultdict

from cg.api import (
    AreaType,
    Card,
    CardType,
    Observation,
    OptionType,
    Pokemon,
    SelectContext,
    all_card_data,
    to_observation_class,
)

"""
Dragapult ex Deck
このデッキはドラパルトexで継続して攻めつつ、サマヨール/ヨノワールでダメージをかさ増しします。
相手の残りサイド枚数に応じて、特性を使うかどうかを切り替えます。
"""

file_path = "deck.csv"
if not os.path.exists(file_path):
    file_path = "/kaggle_simulations/agent/" + file_path
with open(file_path, "r") as file:
    csv = [line.strip() for line in file.read().splitlines() if line.strip()]
my_deck = [int(csv[i]) for i in range(60)]

all_card = all_card_data()
card_table = {card.cardId: card for card in all_card}

# Deck list
Dreepy = 119
Drakloak = 120
Dragapult_ex = 121
Duskull = 131
Dusclops = 132
Dusknoir = 133
Fezandipiti_ex = 140
Budew = 235
Meowth_ex = 1071
Rare_Candy = 1079
Unfair_Stamp = 1080
Buddy_Buddy_Poffin = 1086
Night_Stretcher = 1097
Crushing_Hammer = 1120
Ultra_Ball = 1121
Poke_Pad = 1152
Boss_Orders = 1182
Crispin = 1198
Lillie_Determination = 1227
Lucian = 1237
Rosas_Encouragement = 1240
Jamming_Tower = 1246
Team_Rocket_Watchtower = 1256
Basic_Fire_Energy = 2
Basic_Psychic_Energy = 5


def get_card(
    obs: Observation, area: AreaType, index: int, player_index: int
) -> Pokemon | Card | None:
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


def is_ready_dragapult(card: Pokemon | None) -> bool:
    return card is not None and card.id == Dragapult_ex and len(card.energies) >= 2


def build_remaining_counts(obs: Observation, my_index: int) -> defaultdict[int, int]:
    counts: defaultdict[int, int] = defaultdict(int)
    for card_id in my_deck:
        counts[card_id] += 1

    state = obs.current
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    def consume(card: Card | Pokemon | None) -> None:
        if card is None:
            return
        counts[card.id] -= 1
        if isinstance(card, Pokemon):
            for attached in card.energyCards:
                counts[attached.id] -= 1
            for tool in card.tools:
                counts[tool.id] -= 1

    for card in my_state.hand:
        consume(card)
    for card in my_state.discard:
        consume(card)
    for card in my_state.active:
        consume(card)
    for card in my_state.bench:
        consume(card)
    for card in op_state.active:
        consume(card)
    for card in op_state.bench:
        consume(card)
    for card in state.stadium:
        consume(card)
    if state.looking is not None:
        for card in state.looking:
            consume(card)
    if obs.select.deck is not None:
        for card in obs.select.deck:
            consume(card)

    for card_id in list(counts.keys()):
        if counts[card_id] < 0:
            counts[card_id] = 0
    return counts


def prize_count(pokemon: Pokemon) -> int:
    data = card_table.get(pokemon.id)
    if data is None:
        return 1
    if getattr(data, "megaEx", False):
        return 3
    if getattr(data, "ex", False):
        return 2
    return 1


def pokemon_target_score(pokemon: Pokemon, op_prizes_left: int, damage: int = 0) -> int:
    data = card_table.get(pokemon.id)
    score = prize_count(pokemon) * 1000 + pokemon.hp + len(pokemon.energies) * 120
    if data is not None:
        if getattr(data, "stage2", False):
            score += 250
        elif getattr(data, "stage1", False):
            score += 130

    if pokemon.id == Dragapult_ex:
        score += 400
    elif pokemon.id == Dusknoir:
        score += 300
    elif pokemon.id == Dusclops:
        score += 180

    if op_prizes_left <= 2:
        score += 700
    elif op_prizes_left <= 4:
        score += 350

    if damage > 0 and pokemon.hp <= damage:
        score += 1400
    elif damage > 0 and pokemon.hp <= damage + 60:
        score += 500

    return score


def should_use_cursed_blast(card_id: int, op_prizes_left: int) -> bool:
    if card_id == Dusknoir:
        return op_prizes_left <= 4
    if card_id == Dusclops:
        return op_prizes_left <= 3
    return False


def setup_score(card: Pokemon | Card) -> int:
    if card.id == Dreepy:
        return 52000
    if card.id == Duskull:
        return 50000
    if card.id == Dragapult_ex:
        return 42000
    if card.id == Dusclops:
        return 33000
    if card.id == Dusknoir:
        return 31000
    if card.id == Fezandipiti_ex:
        return 15000
    if card.id == Meowth_ex:
        return 12000
    if card.id == Budew:
        return 9000
    return 1000


def supporter_score(
    card_id: int, my_state, op_state, field_counts, remaining_counts
) -> int:
    op_prizes_left = len(op_state.prize)
    main_ready = field_counts[Dragapult_ex] >= 1 and any(
        is_ready_dragapult(card)
        for card in list(my_state.active) + list(my_state.bench)
    )

    if card_id == Crispin:
        if (
            remaining_counts[Basic_Fire_Energy] > 0
            and remaining_counts[Basic_Psychic_Energy] > 0
        ):
            return 26000 if not main_ready else 18000
        return 8000
    if card_id == Lillie_Determination:
        return 24000 if len(my_state.hand) <= 4 else 14000
    if card_id == Boss_Orders:
        return 18000 if op_prizes_left <= 2 else 11000
    if card_id == Rosas_Encouragement:
        return 16000 if len(my_state.prize) > len(op_state.prize) else 1500
    if card_id == Lucian:
        return 7000 if len(my_state.hand) <= 3 else 1000
    if card_id == Jamming_Tower:
        return 6000
    if card_id == Team_Rocket_Watchtower:
        return 5000
    if card_id == Unfair_Stamp:
        return 22000 if op_prizes_left <= 4 else 10000
    return -1


def hand_score(
    card_id: int,
    my_state,
    op_state,
    field_counts,
    hand_counts,
    discard_counts,
    remaining_counts,
) -> int:
    op_prizes_left = len(op_state.prize)

    if card_id == Dreepy:
        return 52000 if field_counts[Dreepy] == 0 else 24000
    if card_id == Drakloak:
        return 38000 if field_counts[Dreepy] >= 1 else 12000
    if card_id == Dragapult_ex:
        if field_counts[Dragapult_ex] >= 2:
            return 3000
        if field_counts[Dreepy] >= 1 and hand_counts[Rare_Candy] >= 1:
            return 65000
        if field_counts[Drakloak] >= 1:
            return 52000
        return 28000
    if card_id == Duskull:
        return 50000 if field_counts[Duskull] == 0 else 22000
    if card_id == Dusclops:
        return 36000 if field_counts[Duskull] >= 1 else 18000
    if card_id == Dusknoir:
        if field_counts[Dusclops] >= 1:
            return 50000
        if field_counts[Duskull] >= 1 and hand_counts[Rare_Candy] >= 1:
            return 56000
        return 22000
    if card_id == Fezandipiti_ex:
        return 22000 if len(my_state.prize) <= 4 else 7000
    if card_id == Budew:
        return 18000 if field_counts[Budew] == 0 else 5000
    if card_id == Meowth_ex:
        return 26000 if len(my_state.hand) <= 4 else 13000
    if card_id == Rare_Candy:
        if field_counts[Dreepy] >= 1 and hand_counts[Dragapult_ex] >= 1:
            return 60000
        if field_counts[Duskull] >= 1 and hand_counts[Dusknoir] >= 1:
            return 56000
        return 6000
    if card_id == Buddy_Buddy_Poffin:
        return 42000 if remaining_counts[Dreepy] + remaining_counts[Duskull] > 0 else -1
    if card_id == Night_Stretcher:
        if (
            discard_counts[Dreepy] > 0
            or discard_counts[Duskull] > 0
            or discard_counts[Basic_Fire_Energy] > 0
            or discard_counts[Basic_Psychic_Energy] > 0
        ):
            return 36000
        return -1
    if card_id == Crushing_Hammer:
        return 15000 if op_prizes_left <= 4 else 7000
    if card_id == Ultra_Ball:
        if (
            remaining_counts[Dreepy]
            + remaining_counts[Duskull]
            + remaining_counts[Dragapult_ex]
            + remaining_counts[Dusknoir]
            + remaining_counts[Dusclops]
            > 0
        ):
            return 40000
        return 1000
    if card_id == Poke_Pad:
        if (
            remaining_counts[Dreepy]
            + remaining_counts[Duskull]
            + remaining_counts[Drakloak]
            + remaining_counts[Dusclops]
            > 0
        ):
            return 24000
        return -1
    if card_id in (Basic_Fire_Energy, Basic_Psychic_Energy):
        if field_counts[Dragapult_ex] >= 1 and op_prizes_left <= 2:
            return -1
        if field_counts[Dragapult_ex] >= 1 or field_counts[Dusknoir] >= 1:
            return 20000
        return 10000
    return 2000


def attach_score(
    attach_id: int, pokemon: Pokemon, active: bool, op_prizes_left: int
) -> int:
    energy_count = len(pokemon.energies)
    score = 1000

    if pokemon.id == Dragapult_ex:
        score += 22000
        if energy_count == 0:
            score += 2000
        elif energy_count == 1:
            score += 5000
        else:
            score -= 3000
        if active:
            score += 3500
        if op_prizes_left <= 2 and energy_count >= 2:
            score += 3500
    elif pokemon.id == Dreepy:
        score += 3500
        if active:
            score -= 1200
    elif pokemon.id == Drakloak:
        score += 6000
    elif pokemon.id == Duskull:
        score += 2500
        if active:
            score -= 1000
    elif pokemon.id == Dusclops:
        score += 4500
    elif pokemon.id == Dusknoir:
        score += 6000
    elif pokemon.id in (Meowth_ex, Fezandipiti_ex):
        score += 1000
        if active:
            score -= 1500

    if attach_id == Basic_Psychic_Energy and pokemon.id in (
        Dragapult_ex,
        Dusclops,
        Dusknoir,
    ):
        score += 2000
    if attach_id == Basic_Fire_Energy and pokemon.id == Dragapult_ex:
        score += 2000
    return score


def main_attack_score(attack_id: int, op_active_hp: int, op_prizes_left: int) -> int:
    if attack_id == 154:
        score = 50000
        if op_prizes_left <= 2:
            score += 12000
        elif op_prizes_left <= 4:
            score += 4000
        if op_active_hp <= 200:
            score += 1500
        return score
    return 1000 + attack_id


def choose_indices(scores: list[int], select) -> list[int]:
    order = [
        i for i, _ in sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    ]
    output: list[int] = []
    for i, index in enumerate(order[: select.maxCount]):
        if scores[index] >= 0 or i < select.minCount:
            output.append(index)
    return output


def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        return my_deck

    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    remaining_counts = build_remaining_counts(obs, my_index)

    field_counts: defaultdict[int, int] = defaultdict(int)
    hand_counts: defaultdict[int, int] = defaultdict(int)
    discard_counts: defaultdict[int, int] = defaultdict(int)

    ready_active_dragapult = -1
    ready_bench_dragapult = -1
    ready_dusclops = -1
    ready_dusknoir = -1

    for i, card in enumerate(my_state.active):
        if card is None:
            continue
        field_counts[card.id] += 1
        if isinstance(card, Pokemon):
            if is_ready_dragapult(card):
                ready_active_dragapult = i
            elif card.id == Dusclops:
                ready_dusclops = i
            elif card.id == Dusknoir:
                ready_dusknoir = i

    for i, card in enumerate(my_state.bench):
        if card is None:
            continue
        field_counts[card.id] += 1
        if isinstance(card, Pokemon):
            if is_ready_dragapult(card):
                ready_bench_dragapult = i
            elif card.id == Dusclops:
                ready_dusclops = i
            elif card.id == Dusknoir:
                ready_dusknoir = i

    for card in my_state.hand:
        hand_counts[card.id] += 1
    for card in my_state.discard:
        discard_counts[card.id] += 1

    op_active_hp = 0
    for card in op_state.active:
        if card is not None:
            op_active_hp = card.hp

    op_prizes_left = len(op_state.prize)

    switch_index = -1
    if ready_active_dragapult >= 0:
        switch_index = ready_active_dragapult
    elif ready_bench_dragapult >= 0:
        switch_index = ready_bench_dragapult

    scores: list[int] = []
    for o in select.option:
        score = -1

        if o.type == OptionType.NUMBER:
            score = o.number
        elif o.type == OptionType.YES:
            score = 1
        elif o.type == OptionType.CARD:
            card = get_card(obs, o.area, o.index, o.playerIndex)
            if card is not None:
                if context in (
                    SelectContext.SWITCH,
                    SelectContext.TO_ACTIVE,
                    SelectContext.SETUP_ACTIVE_POKEMON,
                ):
                    score = setup_score(card)
                    if o.index == switch_index:
                        score += 18000
                    if card.id == Dragapult_ex:
                        score += 2000
                    elif card.id in (Dusclops, Dusknoir):
                        score += 1000
                elif context in (
                    SelectContext.SETUP_BENCH_POKEMON,
                    SelectContext.TO_BENCH,
                    SelectContext.TO_HAND,
                ):
                    score = setup_score(card)
                elif context == SelectContext.DISCARD:
                    if card.id in (Basic_Fire_Energy, Basic_Psychic_Energy):
                        score = 40000
                    elif card.id in (Dreepy, Duskull):
                        score = 3000
                    elif card.id in (Dragapult_ex, Dusclops, Dusknoir):
                        score = 1000
                    else:
                        score = 500
                    if hand_counts[card.id] >= 2:
                        score += 5000
                    hand_counts[card.id] -= 1
                elif context in (
                    SelectContext.DAMAGE_COUNTER,
                    SelectContext.DAMAGE_COUNTER_ANY,
                ):
                    damage = (
                        130
                        if select.contextCard is not None
                        and select.contextCard.id == Dusknoir
                        else 50
                    )
                    score = pokemon_target_score(card, op_prizes_left, damage)
                    if card.id in (Dusknoir, Dusclops):
                        if should_use_cursed_blast(card.id, op_prizes_left):
                            score += 5000 if card.id == Dusknoir else 2500
                        else:
                            score = -1
                elif context == SelectContext.ATTACH_FROM:
                    context_card_id = (
                        select.contextCard.id if select.contextCard is not None else 0
                    )
                    score = attach_score(
                        context_card_id, card, o.area == AreaType.ACTIVE, op_prizes_left
                    )
        elif o.type in (OptionType.ENERGY_CARD, OptionType.ENERGY):
            if o.playerIndex != my_index:
                score = 10
        elif o.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, o.index, my_index)
            if card is not None:
                if card_table[card.id].cardType == CardType.SUPPORTER:
                    score = supporter_score(
                        card.id, my_state, op_state, field_counts, remaining_counts
                    )
                elif card.id in (Dreepy, Duskull, Fezandipiti_ex, Meowth_ex, Budew):
                    score = setup_score(card)
                elif card.id in (
                    Dragapult_ex,
                    Dusclops,
                    Dusknoir,
                    Rare_Candy,
                    Buddy_Buddy_Poffin,
                    Ultra_Ball,
                    Night_Stretcher,
                    Crushing_Hammer,
                    Poke_Pad,
                    Unfair_Stamp,
                    Jamming_Tower,
                    Team_Rocket_Watchtower,
                ):
                    score = hand_score(
                        card.id,
                        my_state,
                        op_state,
                        field_counts,
                        hand_counts,
                        discard_counts,
                        remaining_counts,
                    )
                else:
                    score = 1000
        elif o.type == OptionType.ATTACH:
            card = get_card(obs, o.area, o.index, my_index)
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            if card is not None and pokemon is not None:
                score = attach_score(
                    card.id, pokemon, o.inPlayArea == AreaType.ACTIVE, op_prizes_left
                )
        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            if pokemon is not None:
                score = len(pokemon.energies) * 1000
                if pokemon.id == Dreepy:
                    score += 40000
                    if (
                        hand_counts[Dragapult_ex] >= 1
                        or remaining_counts[Dragapult_ex] > 0
                    ):
                        score += 9000
                elif pokemon.id == Duskull:
                    score += 38000
                    if hand_counts[Dusclops] >= 1 or remaining_counts[Dusclops] > 0:
                        score += 5000
                    if hand_counts[Dusknoir] >= 1 or remaining_counts[Dusknoir] > 0:
                        score += 4000
                elif pokemon.id == Dusclops:
                    score += 34000
                    if hand_counts[Dusknoir] >= 1 or remaining_counts[Dusknoir] > 0:
                        score += 6000
                    if op_prizes_left <= 4:
                        score += 4000
                elif pokemon.id == Dragapult_ex:
                    score += 15000
        elif o.type == OptionType.ABILITY:
            card = get_card(obs, o.area, o.index, my_index)
            if card is not None:
                if card.id in (Dusclops, Dusknoir):
                    score = (
                        9000 if should_use_cursed_blast(card.id, op_prizes_left) else -1
                    )
                    if card.id == Dusknoir and op_prizes_left <= 2:
                        score += 3000
                else:
                    score = 1000
        elif o.type == OptionType.RETREAT:
            if ready_active_dragapult >= 0 or ready_bench_dragapult >= 0:
                score = 18000
            elif ready_dusclops >= 0 or ready_dusknoir >= 0:
                score = 6000
            else:
                score = -1
        elif o.type == OptionType.ATTACK:
            score = main_attack_score(o.attackId, op_active_hp, op_prizes_left)

        scores.append(score)

    order = [
        i for i, _ in sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    ]
    output: list[int] = []
    for i, index in enumerate(order[: select.maxCount]):
        if scores[index] >= 0 or i < select.minCount:
            output.append(index)
    return output
