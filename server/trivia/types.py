from enum import Enum
from typing import TypedDict

Token = str
UserId = int
HP = int


class PlayerData(TypedDict):
    user_id: UserId
    hp: HP


class LobbyState(Enum):
    WAITING = 1
    IN_PROGRESS = 2
    FINISHED = 3


class GameStatus(Enum):
    DRAW = 1
    LOSS = 2
    WIN = 3


class BaseEvent(TypedDict):
    type: str


class GameEndEvent(BaseEvent):
    users: dict[UserId, GameStatus]
