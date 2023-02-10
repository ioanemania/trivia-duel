from typing import TypedDict, Literal, NamedTuple

from django.db.models import IntegerChoices

Token = str
UserId = int
HP = int


class PlayerData(TypedDict):
    name: str
    hp: HP


class GameType(IntegerChoices):
    RANKED = 1
    NORMAL = 2
    TRAINING = 3


class LobbyState(IntegerChoices):
    WAITING = 1
    IN_PROGRESS = 2
    FINISHED = 3


class GameStatus(IntegerChoices):
    DRAW = 1
    LOSS = 2
    WIN = 3


class UserStatus(TypedDict):
    status: GameStatus
    rank_gain: int


class TriviaAPIQuestion(TypedDict):
    category: str
    type: Literal["boolean"] | Literal["multiple"]
    difficulty: Literal["easy"] | Literal["medium"] | Literal["hard"]
    question: str
    correct_answer: str
    incorrect_answers: list[str]


class TriviaAPIQuestionsResponse(TypedDict):
    """
    The expected format of the response received from
    the Trivia API when requesting questions
    """

    response_code: int
    results: list[TriviaAPIQuestion]


class CorrectAnswer(NamedTuple):
    answer: str
    difficulty: Literal["easy"] | Literal["medium"] | Literal["hard"]


class BaseEvent(TypedDict):
    type: str


class ServerEvent(BaseEvent):
    """Event that is sent by the server"""

    pass


class ClientEvent(BaseEvent):
    """Event that is sent by the client"""

    pass


class GameEndEvent(ServerEvent):
    users: dict[UserId, UserStatus]


class QuestionAnsweredEvent(ClientEvent):
    answer: str


class FiftyRequestedEvent(ClientEvent):
    answers: list[str]
