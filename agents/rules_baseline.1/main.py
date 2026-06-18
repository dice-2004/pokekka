import os
import random

from cg.api import Observation, to_observation_class


def read_deck_csv() -> list[int]:
    """Read deck.csv.

    Returns:
        list[int]: A list of card IDs in the deck.
    """
    file_path = "deck.csv"
    if not os.path.exists(file_path):
        file_path = "/kaggle_simulations/agent/" + file_path
    with open(file_path, "r") as file:
        csv = file.read().split("\n")
    deck = []
    for i in range(60):
        deck.append(int(csv[i]))
    return deck


def agent(obs_dict: dict) -> list[int]:
    """Rules Baseline Agent for testing."""
    obs: Observation = to_observation_class(obs_dict)
    if obs.select == None:
        # Initial selection
        return read_deck_csv()

    # Just randomly select for now (same as sample submission, but can be customized)
    return random.sample(
        list(range(len(obs.select.option))), obs.select.maxCount
    )
