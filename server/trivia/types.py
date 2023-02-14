from typing import Literal, NamedTuple, TypedDict

from django.db.models import IntegerChoices

Token = str
UserId = int
HP = int
Difficulty = Literal["easy"] | Literal["medium"] | Literal["hard"]
QuestionType = Literal["boolean"] | Literal["multiple"]


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
    """
    The expected format of a question received from
    the Trivia API.
    """

    category: str
    type: QuestionType
    difficulty: Difficulty
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


class FormattedQuestion(TypedDict):
    category: str
    question: str
    answers: list[str]
    difficulty: Difficulty
    duration: int
    type: QuestionType


class CorrectAnswer(NamedTuple):
    answer: str
    difficulty: Difficulty


class BaseEvent(TypedDict):
    """
    Base event. All events are expected to have a 'type' associated with them.
    """

    type: str


class ServerEvent(BaseEvent):
    """Event that is sent by the server"""

    pass


class ClientEvent(BaseEvent):
    """Event that is sent by the client"""

    pass


class GamePrepareEvent(ServerEvent):
    pass


class GameStartEvent(ServerEvent):
    users: dict[str, str]
    duration: int


class GameEndEvent(ServerEvent):
    users: dict[str, UserStatus]


class QuestionDataEvent(ServerEvent):
    questions: list[FormattedQuestion]


class QuestionNextEvent(ServerEvent):
    pass


class UserAnsweredEvent(ServerEvent):
    user_id: UserId
    correctly: bool
    correct_answer: str
    damage: int


class QuestionResultEvent(ServerEvent):
    correctly: bool
    correct_answer: str
    damage: int


class OpponentAnsweredEvent(ServerEvent):
    correctly: bool
    damage: int


class QuestionAnsweredEvent(ClientEvent):
    answer: str


class FiftyRequestedEvent(ClientEvent):
    answers: list[str]
