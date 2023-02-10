import secrets

import requests
from django.conf import settings

from trivia.models import PlayerData
from trivia.types import TriviaAPIQuestion


class TriviaAPIClient:
    @staticmethod
    def get_questions(token: str = None) -> list[TriviaAPIQuestion]:
        # TODO: Refactor URL construction
        url = settings.TRIVIA_API_URL + (f"&token={token}" if token else "")

        response = requests.get(url)
        response.raise_for_status()

        return response.json()["results"]

    @staticmethod
    def get_token() -> str:
        response = requests.get(settings.TRIVIA_API_TOKEN_URL)
        response.raise_for_status()

        return response.json()["token"]


def generate_lobby_token_and_data(user) -> tuple[str, PlayerData]:
    data = PlayerData(user_id=user.id, name=user.username, hp=100)
    token = secrets.token_urlsafe(16)

    return token, data


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
