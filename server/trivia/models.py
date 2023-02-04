from typing import Dict, TypedDict
from enum import Enum

from django.db import models
from django.contrib.auth import get_user_model
from redis_om import JsonModel, Field, Migrator

from trivia.types import Token, PlayerData, LobbyState, GameStatus, GameType

User = get_user_model()


class Lobby(JsonModel):
    name: str = Field(primary_key=True)
    user_count: int = 0
    users: Dict[Token, PlayerData] = {}
    current_answer_count: int = 0
    current_question_count: int = 0
    state: LobbyState = LobbyState.WAITING
    ranked: int = Field(index=True, default=0)
    trivia_token: str = ""


class Game(models.Model):
    type = models.IntegerField(choices=GameType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    players = models.ManyToManyField(User, through="UserGame", related_name="games")


class UserGame(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    status = models.IntegerField(choices=GameStatus.choices)
    rank = models.PositiveIntegerField()
    extra_data = models.JSONField(null=True)


Migrator().run()
