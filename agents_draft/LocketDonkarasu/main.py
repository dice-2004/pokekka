import os
import sys
from collections import defaultdict

from agents_draft.LocketDonkarasu.cg.api import (
    AreaType,
    CardType,
    Log,
    LogType,
    Observation,
    SelectContext,
    OptionType,
    Card,
    Pokemon,
    State,
    all_card_data,
    to_observation_class,
)

"""
Team Rocket's Honchkrow Deck
Advanced Level
This deck focuses on establishing Honchkrow early, discarding only the minimum Team Rocket supporters needed for Rocket Feathers, and shifting to Porygon2 / Porygon-Z as late-game damage.
"""

# Load deck.csv in the dataset
file_path = "deck.csv"
if not os.path.exists(file_path):
    file_path = "/kaggle_simulations/agent/" + file_path
with open(file_path, "r") as file:
    csv = file.read().split("\n")
my_deck = []
for i in range(60):
    my_deck.append(int(csv[i]))

# Load all card data from the API's helper function
all_card = all_card_data()
# Create a lookup table (dictionary) to quickly access card data by its cardId
card_table = {c.cardId: c for c in all_card}

# Decklist
Team_Rocket_s_Murkrow = 463  # ×4
Team_Rocket_s_Honchkrow = 891  # ×3
Team_Rocket_s_Porygon = 473  # ×2
Team_Rocket_s_Porygon2 = 474  # ×2
Team_Rocket_s_Porygon_Z = 475  # ×1
Team_Rocket_s_Articuno = 414  # ×1
Roto_Stick = 1077  # ×2
Air_Balloon = 1174  # ×1
Brave_Bangle = 1175  # ×1
Miracle_Headset = 1109  # ×1
Team_Rocket_s_Transceiver = 1134  # ×4
Night_Stretcher = 1097  # ×2
Poke_Pad = 1152  # ×4
Team_Rocket_s_Ariana = 1216  # ×4
Team_Rocket_s_Archer = 1217  # ×4
Team_Rocket_s_Giovanni = 1218  # ×4
Team_Rocket_s_Petrel = 1219  # ×4
Team_Rocket_s_Proton = 1220  # ×4
Team_Rocket_s_Factory = 1257  # ×4
Team_Rocket_s_Energy = 15  # ×4
Ignition_Energy = 17  # ×4

# Compatibility aliases for the existing agent logic.
# These names are retained so the rest of the file can be updated incrementally.
Dreepy = Team_Rocket_s_Murkrow
Drakloak = Team_Rocket_s_Honchkrow
Dragapult_ex = Team_Rocket_s_Porygon
Fezandipiti_ex = Team_Rocket_s_Porygon2
Latias_ex = Team_Rocket_s_Porygon_Z
Budew = Team_Rocket_s_Articuno
Meowth_ex = Team_Rocket_s_Articuno
Rare_Candy = Air_Balloon
Unfair_Stamp = Brave_Bangle
Buddy_Buddy_Poffin = Miracle_Headset
Night_Stretcher = Team_Rocket_s_Transceiver
Crushing_Hammer = Night_Stretcher
Ultra_Ball = Poke_Pad
Poke_Pad = Team_Rocket_s_Ariana
Lucky_Helmet = Team_Rocket_s_Archer
Boss_Orders = Team_Rocket_s_Giovanni
Crispin = Team_Rocket_s_Petrel
Brock_Scouting = Team_Rocket_s_Proton
Lillie_Determination = Team_Rocket_s_Factory
Team_Rocket_Watchtower = Team_Rocket_s_Factory
Basic_Fire_Energy = Team_Rocket_s_Energy
Basic_Psychic_Energy = Ignition_Energy

Murkrow = Team_Rocket_s_Murkrow
Honchkrow = Team_Rocket_s_Honchkrow
Porygon = Team_Rocket_s_Porygon
Porygon2 = Team_Rocket_s_Porygon2
Porygon_Z = Team_Rocket_s_Porygon_Z
Articuno = Team_Rocket_s_Articuno
Ariana = Team_Rocket_s_Ariana
Archer = Team_Rocket_s_Archer
Giovanni = Team_Rocket_s_Giovanni
Petrel = Team_Rocket_s_Petrel
Proton = Team_Rocket_s_Proton
Factory = Team_Rocket_s_Factory
Rocket_Energy = Team_Rocket_s_Energy

TEAM_ROCKET_BASICS = {Murkrow, Porygon}
TEAM_ROCKET_EVOLUTIONS = {Honchkrow, Porygon2, Porygon_Z}
TEAM_ROCKET_POKEMON = TEAM_ROCKET_BASICS | TEAM_ROCKET_EVOLUTIONS | {Articuno}
TEAM_ROCKET_SUPPORTERS = {
    Team_Rocket_s_Ariana,
    Team_Rocket_s_Archer,
    Team_Rocket_s_Giovanni,
    Team_Rocket_s_Petrel,
    Team_Rocket_s_Proton,
}
ROCKET_SUPPORT_DISCARD_PRIORITY = {
    Team_Rocket_s_Proton: 0,
    Team_Rocket_s_Archer: 1,
    Team_Rocket_s_Giovanni: 2,
    Team_Rocket_s_Petrel: 3,
    Team_Rocket_s_Ariana: 4,
}
ROCKET_FEATHERS_ATTACK_ID = 1285
POLYGON2_ATTACK_ID = 670
POLYGONZ_ATTACK_ID = 671

UNNECESSARY = -10000000


class AttackPlan:
    attack: int = 0
    counter: list[int] = []


can_switch = False
can_attack = False
can_main_attack = False
can_energy_attach = False
use_support = 0  # The Supporter card planned for use.
bench_attacker = False  # Whether there is a Benched Pokémon that is ready to attack
pre_turn_log: list[Log] = []
current_turn_log: list[Log] = []

prize: list[int] = []
card_counts: defaultdict[int, int] = defaultdict(int)
serial_set: set[int] = set()
plan_a = AttackPlan()
plan_b = AttackPlan()
preferred_attack_id = ROCKET_FEATHERS_ATTACK_ID
rocket_feathers_required_support = 0
rocket_feathers_discard_budget = 0
rocket_support_discard_count = 0
opponent_active_hp = 0
rocket_feathers_discard_indices: set[int] = set()


def no_damage_dex(id: int) -> bool:
    """Returns whether the target should be deprioritized for direct Rocket Feathers damage."""
    return id in {158, 207, 330, 345}


def no_damage_counter(pokemon: Pokemon) -> bool:
    """Returns whether the target is bad for counter-based bench damage planning."""
    if (
        pokemon.id == 28
        or pokemon.id == 199
        or pokemon.id == 203
        or pokemon.id == 207
        or pokemon.id == 362
        or pokemon.id == 1136
    ):
        return True
    for card in pokemon.energyCards:
        # Mist Energy, Rock Fighting Energy
        if card.id == 11 or card.id == 20:
            return True
    return False


def prize_count(pokemon: Pokemon, is_attack_damage: bool) -> int:
    """Calculate Prize cards yielded by KOing opponent's Pokémon."""
    data = card_table[pokemon.id]
    count = 3 if data.megaEx else 2 if data.ex else 1
    if is_attack_damage:
        for card in pokemon.energyCards:
            if card.id == 12:  # Legacy Energy
                count -= 1
        for card in pokemon.tools:
            if card.id == 1172 and "Lillie" in data.name:  # Lillie’s Pearl
                count -= 1
    return max(0, count)


def pokemon_score(pokemon: Pokemon, is_attack_damage: bool) -> int:
    """Heuristically evaluates the tactical worth of targeting a specific Pokémon on the opponent's field."""
    data = card_table[pokemon.id]
    score = prize_count(pokemon, is_attack_damage) * 1000
    score += len(pokemon.energies) * 150
    score += len(pokemon.tools) * 100
    if data.stage2:
        score += 250
    elif data.stage1:
        score += 130

    id = pokemon.id
    # Squawkabilly ex, Noctowl, Fan Rotom, Archaludon ex
    if id == 144 or id == 322 or id == 323 or id == 337:
        score -= 200
    if id == 112 and len(pokemon.energies) >= 1:  # Munkidori
        score += 300
    score += pokemon.hp
    if pokemon.id == Articuno:
        score -= 500
    return score


def add_card_count(card: Card | Pokemon | None, my_index: int):
    if card == None:
        return
    if isinstance(card, Pokemon) or card.playerIndex == my_index:
        if card.serial not in serial_set:
            card_counts[card.id] -= 1
            serial_set.add(card.serial)
    if isinstance(card, Pokemon):
        for c in card.energyCards:
            add_card_count(c, my_index)
        for c in card.tools:
            add_card_count(c, my_index)
        for c in card.preEvolution:
            add_card_count(c, my_index)


def set_card_counts(obs: Observation, my_index: int):
    card_counts.clear()
    serial_set.clear()
    for id in my_deck:
        card_counts[id] += 1

    state = obs.current
    my_state = state.players[my_index]
    for card in my_state.hand:
        add_card_count(card, my_index)
    for card in my_state.discard:
        add_card_count(card, my_index)
    for card in my_state.bench:
        add_card_count(card, my_index)
    for card in my_state.active:
        add_card_count(card, my_index)
    for card in state.stadium:
        add_card_count(card, my_index)
    if state.looking != None:
        for card in state.looking:
            add_card_count(card, my_index)
    add_card_count(obs.select.effect, my_index)


def get_card(
    obs: Observation, area: AreaType, index: int, player_index: int
) -> Pokemon | Card | None:
    """Helper function to safely extract a Card or Pokemon object from specific zones."""
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


def main_option_proc(obs: Observation, damage: int):
    state = obs.current
    select = obs.select
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    global can_switch
    global can_attack
    global can_main_attack
    global can_energy_attach
    global preferred_attack_id
    global rocket_feathers_required_support
    global rocket_feathers_discard_budget
    global rocket_support_discard_count
    global opponent_active_hp
    global rocket_feathers_discard_indices

    can_switch = False
    can_attack = False
    can_main_attack = False
    can_energy_attach = False
    preferred_attack_id = ROCKET_FEATHERS_ATTACK_ID
    for o in select.option:
        if o.type == OptionType.RETREAT:
            can_switch = True
        elif o.type == OptionType.ATTACK:
            can_attack = True
            if o.attackId == ROCKET_FEATHERS_ATTACK_ID:
                can_main_attack = True

    plan_a.attack = -1
    plan_b.attack = -1
    rocket_feathers_required_support = 0
    rocket_feathers_discard_budget = 0
    rocket_support_discard_count = 0
    rocket_feathers_discard_indices = set()

    opponent_active_hp = op_state.active[0].hp if len(op_state.active) > 0 else 0
    if opponent_active_hp > 0:
        rocket_feathers_required_support = (opponent_active_hp + 59) // 60

    if not can_attack:
        return

    team_rocket_supporters_in_hand = 0
    for card in my_state.hand:
        if card.id in TEAM_ROCKET_SUPPORTERS:
            team_rocket_supporters_in_hand += 1

    if rocket_feathers_required_support > 0:
        if team_rocket_supporters_in_hand >= rocket_feathers_required_support:
            rocket_feathers_discard_budget = rocket_feathers_required_support
        else:
            rocket_feathers_discard_budget = max(0, team_rocket_supporters_in_hand - 1)

    plan_a.attack = 0 if can_main_attack else -1
    plan_b.attack = plan_a.attack


def agent(obs_dict: dict) -> list[int]:
    """Main Agent Function.

    Each element in the returned list must be >= 0 and < len(obs.select.option).
    The list length must be between obs.select.minCount and obs.select.maxCount (inclusive), with no duplicate elements.

    Returns:
        list[int]: A list of option index.
    """
    obs = to_observation_class(obs_dict)
    if obs.select == None:
        # In the initial selection, the obs.select is None, and it is necessary to return the deck.
        # The deck is a list of 60 card IDs.
        # The deck must comply with the Pokémon Trading Card Game rules.
        return my_deck

    global pre_turn_log
    global current_turn_log

    state = obs.current
    select = obs.select
    context = select.context
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]

    if state.turn == 0:
        prize.clear()
        pre_turn_log.clear()
        current_turn_log.clear()
    else:
        for log in obs.logs:
            current_turn_log.append(log)
            if log.type == LogType.TURN_END:
                pre_turn_log = current_turn_log
                current_turn_log = []

    pre_ko = False
    no_item = False
    for log in pre_turn_log:
        if log.type == LogType.ATTACK:
            if log.attackId == 323:  # Itchy Pollen
                no_item = True
        elif log.type == LogType.MOVE_CARD:
            if (
                log.playerIndex == my_index
                and (log.fromArea == AreaType.BENCH or log.fromArea == AreaType.ACTIVE)
                and log.toArea == AreaType.DISCARD
            ):
                pre_ko = True

    if select.deck != None:
        set_card_counts(obs, my_index)
        for card in select.deck:
            card_counts[card.id] -= 1
        prize.clear()
        for id in card_counts:
            for _ in range(card_counts[id]):
                prize.append(id)

    set_card_counts(obs, my_index)
    for id in prize:
        card_counts[id] -= 1
    deck_counts = card_counts

    prize_diff = len(my_state.prize) - len(op_state.prize)

    global bench_attacker

    # Number of cards per card ID on the Bench and in the Active Spot
    field_counts = defaultdict(int)
    # Number of cards per card ID in hand
    hand_counts = defaultdict(int)
    # Number of cards per card ID in discard pile
    discard_counts = defaultdict(int)

    active_id = 0
    bench_attacker = False
    can_evolve_dreepy = False
    evolve_dreepy_count = 0
    can_evolve_drakloak = False
    damage = 200
    for card in my_state.active:
        if card == None:
            continue
        active_id = card.id
        field_counts[card.id] += 1
        if not card.appearThisTurn:
            if card.id == Dreepy:
                can_evolve_dreepy = True
                evolve_dreepy_count += 1
            elif card.id == Drakloak:
                can_evolve_drakloak = True
    for card in my_state.bench:
        field_counts[card.id] += 1
        if not card.appearThisTurn:
            if card.id == Dreepy:
                can_evolve_dreepy = True
                evolve_dreepy_count += 1
            elif card.id == Drakloak:
                can_evolve_drakloak = True
        if card.id == Dragapult_ex and len(card.energies) >= 2:
            bench_attacker = True
    main_pokemon_count = (
        field_counts[Dreepy] + field_counts[Drakloak] + field_counts[Dragapult_ex]
    )
    no_more_dex = field_counts[Dragapult_ex] * 2 >= len(op_state.prize)

    stadium_id = 0
    for card in state.stadium:
        stadium_id = card.id

    support_count = 0

    for card in my_state.discard:
        discard_counts[card.id] += 1

    def attach_score(attach_id: int, pokemon: Pokemon, active: bool) -> int:
        """Score for attaching a card to a Pokémon."""
        energy_count = len(pokemon.energies)

        # Tool attachment - high priority for all
        if card_table[attach_id].cardType == CardType.TOOL:
            score = 60000
            if active:
                score += 2000  # Prefer active Pokémon for tools
            # Specific tool priorities
            if attach_id == Air_Balloon:
                if pokemon.id == Articuno:
                    score += 5000  # Critical for wall Pokémon
                else:
                    score += 1000
            elif attach_id == Brave_Bangle:
                if pokemon.id in {Murkrow, Honchkrow}:
                    score += 3000  # Boost main attacker
                else:
                    score += 1000
            return score

        # Energy attachment - Rocket team preference
        if pokemon.id == Articuno:
            # Never attach energy to Articuno - it's a wall
            return -1

        # Rocket's Energy - primary choice for Honchkrow line
        if attach_id == Rocket_Energy:
            if pokemon.id in {Murkrow, Honchkrow}:
                score = 50000  # Very high - provides P+D support
                if active and len(pokemon.energies) < 2:
                    score += 5000  # Attack setup priority
                return score
            else:
                return 100  # Low priority for other Pokémon

        # Ignition Energy - ONLY for immediate attack
        if attach_id == Ignition_Energy:
            if pokemon.id == Honchkrow and active and can_main_attack:
                # Check if can KO with this energy
                if len(op_state.active) > 0:
                    damage_with_ignition = opponent_active_hp  # Placeholder
                    if can_main_attack and len(op_state.active) > 0:
                        return 35000  # High value for finishing blow
                    else:
                        return -1
            else:
                return -1  # Never use for setup

        # Other energies - very low priority for this deck
        # (Not Rocket or Ignition energy types)
        return 100  # Minimal value for non-Rocket energies

    def hand_score(id: int, ignore_count: bool):
        """Evaluate hand card value for Team Rocket's Honchkrow deck."""
        score = 0

        # Pokémon cards - Main attackers
        if id == Murkrow:
            # Setup for Honchkrow evolution
            if field_counts[Honchkrow] == 0 and deck_counts[Honchkrow] > 0:
                score = 50000  # Priority: set up Honchkrow line
            else:
                score = 5000
        elif id == Honchkrow:
            # Main attacker - Rocket Feathers is our primary win condition
            if len(my_state.active) > 0 and my_state.active[0].id != Honchkrow:
                score = 70000  # Very high priority to get into active
            elif field_counts[Honchkrow] == 0:
                score = 65000  # Priority to set up bench Honchkrow
            else:
                score = 3000
        elif id == Porygon:
            # Endgame alternative attacker - low priority
            if rocket_support_discard_count >= 8:
                score = 25000  # Setup when lots of supporters already discarded
            else:
                score = 1000
        elif id == Porygon2:
            # Stage 1 evolution of Porygon
            if field_counts[Porygon] > 0 and rocket_support_discard_count >= 6:
                score = 22000
            else:
                score = 500
        elif id == Porygon_Z:
            # Stage 2 final form - highest endgame potential
            if field_counts[Porygon2] > 0 and rocket_support_discard_count >= 8:
                score = 30000  # Very strong if we have enough discarded supporters
            else:
                score = 100
        elif id == Articuno:
            # Bench protection wall - no energy attachment
            if field_counts[Articuno] == 0 and len(op_state.prize) >= 2:
                score = 8000  # Setup bench wall
            else:
                score = 100

        # Supporter cards - Rocket Team supporters
        elif id == Ariana:
            # Draw support - CRITICAL: preserve when possible for next turn consistency
            # Value: higher with fewer cards in hand (can draw more)
            remaining_hand = 8 - len(my_state.hand)
            if remaining_hand > 0:
                score = 50000 + (remaining_hand * 1000)  # Strong draw incentive
            else:
                score = 30000  # Still valuable even at hand limit
        elif id == Proton:
            # Support fuel - lowest discard priority
            score = 200  # Very low value - should be discarded first to Rocket Feathers
        elif id == Archer:
            # Support fuel - second lowest discard priority
            score = 400  # Low value - second choice for discard
        elif id == Giovanni:
            # Support fuel - third lowest discard priority
            score = 600  # Lower-mid value - third choice for discard
        elif id == Petrel:
            # Support fuel - fourth lowest discard priority (train searcher but value as fuel)
            score = 800  # Lower-mid value - fourth choice for discard

        # Trainer cards - Items
        elif id == Roto_Stick:
            # Supporter search from deck top
            if deck_counts[Ariana] > 0:
                score = 40000  # High value if Ariana still in deck
            else:
                score = 15000
        elif id == Air_Balloon:
            # Retreat cost reduction - for Articuno wall or switching out
            if field_counts[Articuno] > 0 and len(op_state.active) > 0:
                score = 12000  # Useful for wall Pokémon
            else:
                score = 2000
        elif id == Brave_Bangle:
            # Extra damage to opponent EX - helps Rocket Feathers or Polygon
            if len(op_state.active) > 0 and card_table[op_state.active[0].id].ex:
                score = 15000  # Boost if opponent has EX
            else:
                score = 3000
        elif id == Miracle_Headset:
            # Recover supporters from discard - very valuable for consistency
            if len(my_state.discard) > 0:
                score = 35000  # Good value for grind game
            else:
                score = 5000
        elif id == Team_Rocket_s_Transceiver:
            # Specific Rocket supporter search
            score = 38000  # High consistency value
        elif id == Night_Stretcher:
            # Recover Pokémon or Basic Energy from discard
            best_recover = 100
            for card_id in discard_counts:
                if discard_counts[card_id] > 0:
                    card_type = card_table[card_id].cardType
                    if (
                        card_type == CardType.POKEMON
                        or card_type == CardType.BASIC_ENERGY
                    ):
                        best_recover = max(
                            best_recover, hand_score(card_id, ignore_count)
                        )
            score = best_recover
        elif id == Poke_Pad:
            # Pokémon search - look for Honchkrow or Murkrow evolution line
            murkrow_score = hand_score(Murkrow, ignore_count)
            honchkrow_score = hand_score(Honchkrow, ignore_count)
            score = max(murkrow_score, honchkrow_score)
        elif id == Team_Rocket_s_Factory:
            # Stadium - draw 2 after playing Rocket supporter
            if state.supporterPlayed or (not ignore_count and support_count > 0):
                score = 35000  # Good value for draw acceleration
            else:
                score = 2000
        elif id == Team_Rocket_s_Energy:
            # Rocket-specific energy - attach to main attackers
            max_score = 0
            for pokemon in my_state.active:
                if pokemon and pokemon.id in {Murkrow, Honchkrow, Articuno}:
                    max_score = max(max_score, attach_score(id, pokemon, True))
            for pokemon in my_state.bench:
                if pokemon and pokemon.id in {Murkrow, Honchkrow, Articuno}:
                    max_score = max(max_score, attach_score(id, pokemon, False))
            score = max_score if max_score > 0 else 2000
        elif id == Ignition_Energy:
            # Temporary energy - only use if can attack THIS turn and KO
            if can_main_attack and len(op_state.active) > 0:
                if my_state.active and my_state.active[0].id == Honchkrow:
                    if opponent_active_hp <= rocket_feathers_required_support * 60:
                        score = 25000  # Good for finishing blow
                    else:
                        score = -1  # Don't waste on missed KO
                else:
                    score = -1
            else:
                score = -1  # Never use for setup

        # Penalty for duplicates in hand
        if not ignore_count and hand_counts[id] > 0:
            score -= 100000  # Strong penalty for having multiples already

        return score

    global use_support
    if context == SelectContext.MAIN:
        main_option_proc(obs, damage)

        use_support = 0
        if not state.supporterPlayed:
            support_score = 0
            for o in select.option:
                if o.type == OptionType.PLAY:
                    card = get_card(obs, AreaType.HAND, o.index, state.yourIndex)
                    if card_table[card.id].cardType == CardType.SUPPORTER:
                        score = hand_score(card.id, True)
                        if support_score < score:
                            support_score = score
                            use_support = card.id

    hand_scores = []
    negative_hand_count = 0
    for card in my_state.hand:
        score = hand_score(card.id, False)
        hand_scores.append(score)
        if score < 0:
            negative_hand_count += 1
        hand_counts[card.id] += 1
        if (
            card_table[card.id].cardType == CardType.SUPPORTER
            and card.id != Boss_Orders
        ):
            support_count += 1

    no_draw = (
        my_state.deckCount <= 8
    )  # Whether to restrict actions that reduce the deck
    do_switch = not can_main_attack and (
        bench_attacker
        or (active_id != Budew and field_counts[Budew] >= 1 and state.turn >= 2)
    )
    effect_card_id = 0 if select.effect == None else select.effect.id
    context_card_id = 0 if select.contextCard == None else select.contextCard.id

    scores = []  # Score for each action
    for o in select.option:
        score = 0  # The default and baseline score is 0.
        if o.type == OptionType.NUMBER:
            score = o.number
        elif o.type == OptionType.YES:
            if context == SelectContext.IS_FIRST:
                score = -1
            else:
                score = 1
        elif o.type == OptionType.CARD:
            card = get_card(obs, o.area, o.index, o.playerIndex)
            if card != None:
                energy_count = 0
                hp = 0
                if isinstance(card, Pokemon):
                    energy_count = len(card.energies)
                    hp = card.hp
                if (
                    context == SelectContext.SWITCH
                    or context == SelectContext.TO_ACTIVE
                    or context == SelectContext.SETUP_ACTIVE_POKEMON
                ):
                    # Selection of the Pokémon to send to the Active Spot
                    if o.playerIndex == my_index:
                        if card.id == Dreepy:
                            score += 10000
                        elif card.id == Drakloak:
                            if energy_count >= 1:
                                score += 20000
                            else:
                                score -= 10000
                        elif card.id == Dragapult_ex:
                            score += 50000
                        elif card.id == Budew:
                            if context != SelectContext.SWITCH:
                                score += 100000
                            elif not bench_attacker:
                                score += 30000
                        elif card.id == Fezandipiti_ex:
                            score -= 1000
                        elif card.id == Meowth_ex:
                            score -= 2000
                    else:
                        if plan_a.attack == o.index + 1:
                            score += 100000
                    score += energy_count * 1000
                    score += hp
                elif context == SelectContext.SETUP_BENCH_POKEMON:
                    if my_index == state.firstPlayer or card.id != Dreepy:
                        score = -1
                elif (
                    context == SelectContext.TO_BENCH
                    or context == SelectContext.TO_HAND
                ):
                    score = hand_score(card.id, False)
                    hand_counts[card.id] += 1
                    if effect_card_id == Crispin:
                        # Reverse scoring
                        score = 100000 - hand_score(card.id, True)
                elif context == SelectContext.DISCARD:
                    hand_counts[card.id] -= 1
                    if card_table[card.id].cardType == CardType.SUPPORTER:
                        support_count -= 1
                    score = -hand_score(card.id, False)
                elif (
                    context == SelectContext.DAMAGE_COUNTER
                    or context == SelectContext.DAMAGE_COUNTER_ANY
                ):
                    if hp > 0:
                        score = 100000 - 10 * hp + pokemon_score(card, False)
                        if context == SelectContext.DAMAGE_COUNTER:
                            if 210 <= hp <= 230:
                                score += 20000 + hp * 20
                                if o.area == AreaType.ACTIVE:
                                    score += 10000
                            elif 40 <= hp <= 90:
                                score += 10000 + hp * 20
                            elif hp <= 30:
                                score += -10000 + hp * 20
                            if card.id == 133 or card.id == 351:
                                score += 30000
                        else:
                            index = o.index + 1
                            if index in plan_b.counter:
                                score += 100000
                            else:
                                remain_damage = select.remainDamageCounter * 10
                                if 210 <= hp <= 200 + remain_damage:
                                    score += 30000
                                elif 20 <= hp <= 60 + remain_damage:
                                    score += 10000
                                elif hp == 10:
                                    score -= 100000
                            if no_damage_counter(card):
                                score = -1
                elif context == SelectContext.ATTACH_FROM:
                    score = attach_score(
                        context_card_id, card, o.area == AreaType.ACTIVE
                    )
                    if card.id == Dragapult_ex:
                        score += 200
        elif o.type == OptionType.ENERGY_CARD or o.type == OptionType.ENERGY:
            # Discarding energy (Retreat or Crushing Hammer)
            if o.playerIndex != state.yourIndex:
                if o.area == AreaType.BENCH:
                    score = 20
                else:
                    score = 10
                card = get_card(obs, o.area, o.index, o.playerIndex)
                if card_table[card.id].cardType == CardType.SPECIAL_ENERGY:
                    score += 1
        elif o.type == OptionType.PLAY:
            card = get_card(obs, AreaType.HAND, o.index, my_index)
            card_score = hand_scores[o.index]

            # Pokémon cards - Main lineup
            if card.id == Murkrow:
                # Setup for Honchkrow evolution
                if field_counts[Honchkrow] == 0 and deck_counts[Honchkrow] > 0:
                    score = 65000  # High priority: build Honchkrow line
                else:
                    score = 8000
            elif card.id == Honchkrow:
                # Main attacker - very high priority
                score = 70000  # Core win condition
            elif card.id == Porygon:
                # Endgame alternative - low priority
                if rocket_support_discard_count >= 8:
                    score = 25000
                else:
                    score = 2000
            elif card.id == Porygon2:
                # Stage 1 - low priority
                if rocket_support_discard_count >= 6:
                    score = 20000
                else:
                    score = 500
            elif card.id == Porygon_Z:
                # Stage 2 - moderate endgame priority
                if rocket_support_discard_count >= 8:
                    score = 30000
                else:
                    score = 100
            elif card.id == Articuno:
                # Wall Pokémon - conditional setup
                if field_counts[Articuno] == 0 and len(op_state.prize) >= 2:
                    score = 12000  # Bench wall setup
                else:
                    score = 100

            # Supporter cards - Team Rocket supporters
            elif card.id == Ariana:
                # Draw support - preserve as much as possible
                if card_score > 0 and not state.supporterPlayed:
                    score = 55000  # Very high priority
                else:
                    score = -1
            elif card.id == Proton:
                # Support fuel - conditional
                if card_score > 0 and not state.supporterPlayed:
                    score = 5000  # Lower priority for discard
                else:
                    score = -1
            elif card.id == Archer:
                # Support fuel - conditional
                if card_score > 0 and not state.supporterPlayed:
                    score = 7000
                else:
                    score = -1
            elif card.id == Giovanni:
                # Support fuel - conditional
                if card_score > 0 and not state.supporterPlayed:
                    score = 9000
                else:
                    score = -1
            elif card.id == Petrel:
                # Support fuel - conditional
                if card_score > 0 and not state.supporterPlayed:
                    score = 11000
                else:
                    score = -1

            # Trainer cards - Items & Stadium
            elif card.id == Roto_Stick:
                if card_score >= 0:
                    score = 40000  # High value supporter search
                else:
                    score = -1
            elif card.id == Team_Rocket_s_Transceiver:
                if card_score >= 0:
                    score = 42000  # Specific Rocket supporter search
                else:
                    score = -1
            elif card.id == Poke_Pad:
                if deck_counts[Murkrow] + deck_counts[Honchkrow] > 0:
                    score = 45000  # High priority evolution line search
                else:
                    score = -1
            elif card.id == Night_Stretcher:
                if card_score >= 8000:
                    score = 42000  # Recover from discard
                else:
                    score = -1
            elif card.id == Miracle_Headset:
                if len(my_state.discard) > 0:
                    score = 35000  # Recover supporters from discard
                else:
                    score = -1
            elif card.id == Team_Rocket_s_Factory:
                if state.supporterPlayed or support_count > 0:
                    score = 40000  # Stadium for draw acceleration
                else:
                    score = -1
            elif card.id == Air_Balloon:
                score = 15000  # Tool - useful for wall or switching
            elif card.id == Brave_Bangle:
                if len(op_state.active) > 0 and card_table[op_state.active[0].id].ex:
                    score = 18000
                else:
                    score = 5000
            elif no_draw:
                score = -1
            else:
                # Default handling for other items/energies
                score = card_score
        elif o.type == OptionType.ATTACH:
            card = get_card(obs, o.area, o.index, my_index)
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)
            score = attach_score(card.id, pokemon, o.inPlayArea == AreaType.ACTIVE)
        elif o.type == OptionType.EVOLVE:
            pokemon = get_card(obs, o.inPlayArea, o.inPlayIndex, my_index)

            # Murkrow -> Honchkrow: Highest evolution priority
            if pokemon.id == Murkrow:
                score = 120000  # Critical: evolve ASAP to get main attacker
            # Porygon -> Porygon2: Endgame evolution
            elif pokemon.id == Porygon:
                if rocket_support_discard_count >= 5:
                    score = 50000  # Moderate value if already discarded supporters
                else:
                    score = 1000
            # Porygon2 -> Porygon-Z: Endgame evolution
            elif pokemon.id == Porygon2:
                if rocket_support_discard_count >= 8:
                    score = 70000  # High value in endgame
                else:
                    score = 2000
            else:
                score = 10000 + len(pokemon.energies) * 100
        elif o.type == OptionType.ABILITY:
            card = get_card(obs, o.area, o.index, my_index)
            if no_draw:
                score = -1
            elif card.id == 1267:  # Lumiose City
                score = 1
            else:
                score = 40000
        elif o.type == OptionType.RETREAT:
            if do_switch:
                score = 10000
            else:
                score = -1
        elif o.type == OptionType.ATTACK:
            score = o.attackId

        scores.append(score)

    output = []
    if len(scores) >= 1:
        # Select in descending order of score
        sorted_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        for i in range(select.maxCount):
            # If the score is negative, do not select it if skipping is possible
            if (
                sorted_scores[i][1] >= 0
                or select.minCount > i
                or (
                    context != SelectContext.TO_BENCH
                    and context != SelectContext.SETUP_BENCH_POKEMON
                )
            ):
                output.append(sorted_scores[i][0])

    return output
