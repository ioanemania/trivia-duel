from typing import TypedDict

from django.db.models import IntegerChoices

Token = str
UserId = int
HP = int


class PlayerData(TypedDict):
    user_id: UserId
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


class BaseEvent(TypedDict):
    type: str


class GameEndEvent(BaseEvent):
    users: dict[UserId, UserStatus]
