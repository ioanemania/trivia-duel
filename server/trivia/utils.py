from datetime import datetime, timedelta, timezone

import jwt
import requests
from django.conf import settings
from trivia.types import TriviaAPIQuestion


class TriviaAPIClient:
    @staticmethod
    def get_questions(token: str = None) -> list[TriviaAPIQuestion]:
        url = settings.TRIVIA_API_URL + (f"&token={token}" if token else "")

        response = requests.get(url)
        response.raise_for_status()

        return response.json()["results"]

    @staticmethod
    def get_token() -> str:
        response = requests.get(settings.TRIVIA_API_TOKEN_URL)
        response.raise_for_status()

        return response.json()["token"]


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


def generate_lobby_token(user) -> str:
    token = jwt.encode(
        {"id": user.id, "username": user.username, "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=5)},
        settings.SECRET_KEY,
        algorithm="HS256",
    )

    return token


def decode_lobby_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
