import secrets

import requests
from django.conf import settings

from trivia.models import PlayerData


def generate_lobby_token_and_data(user) -> tuple[str, PlayerData]:
    data = PlayerData(user_id=user.id, hp=100)
    token = secrets.token_urlsafe(16)

    return token, data


def get_questions() -> list[dict]:
    response = requests.get(settings.TRIVIA_API_URL)
    response.raise_for_status()

    return response.json()["results"]


def parse_boolean_string(value: str) -> bool:
    """
    Converts a string to a boolean object

    Args:
        value: string to convert

    Returns: a boolean representation of the value

    Raises:
        ValueError: if the value does not correspond to a boolean
    """

    true_false_str = ("true", "false")
    true_false_bool = (True, False)

    return true_false_bool[true_false_str.index(value.lower())]
