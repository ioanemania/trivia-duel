from datetime import datetime, timedelta, timezone

import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from trivia.types import TriviaAPIQuestion

User = get_user_model()


class TriviaAPIClient:
    """Client used to communicated with the Trivia Questions API"""

    @staticmethod
    def get_questions(token: str = None) -> list[TriviaAPIQuestion]:
        """
        Get questions from the API.

        Args:
            token: API token that can be used to track obtained questions.
                   the token guarantees to prevent obtaining repeated questions.

        Returns:
            A list of trivia questions
        """
        url = settings.TRIVIA_API_URL + (f"&token={token}" if token else "")

        response = requests.get(url)
        response.raise_for_status()

        return response.json()["results"]

    @staticmethod
    def get_token() -> str:
        """
        Get a Trivia API token.

        The API token is used as a session identifier, to track previously obtained questions.
        It can be used when requesting questions to guarantee that they won't be repeated.

        Returns:
            the API token
        """
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


def generate_lobby_token(user: User, lobby_name: str) -> str:
    """
    Generate a lobby authentication token.

    The token is a JWT intended to be used by users to connect to the
    GameConsumer websocket consumer.

    The token has a very short lifetime and is intended to be used immediately
    after being obtained.

    Args:
        user: user for which the token is generated for
        lobby_name: name of the lobby for which the token is generated for

    Returns:
        base64 encoded JWT

    """

    token = jwt.encode(
        {
            "id": user.id,
            "username": user.username,
            "lobby_name": lobby_name,
            "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=5),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )

    return token


def decode_lobby_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
