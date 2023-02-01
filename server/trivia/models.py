from typing import Dict, TypedDict

from django.db import models
from django.contrib.auth import get_user_model
from redis_om import JsonModel, Field, Migrator

User = get_user_model()

Token = str


class PlayerData(TypedDict):
    user_id: int
    hp: int


class Lobby(JsonModel):
    name: str = Field(primary_key=True)
    user_count: int = 0
    users: Dict[Token, PlayerData] = {}
    current_answer_count: int = 0
    game_started: bool = False
    is_ranked: int = Field(index=True, default=0)


class Game(models.Model):
    user = models.ForeignKey(User, related_name="games", on_delete=models.CASCADE)
    rank = models.PositiveIntegerField()
    type = models.CharField(max_length=10)  # TODO: Should be a choice
    status = models.CharField(max_length=10)  # TODO: Should be a choice
    extra_data = models.JSONField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)


Migrator().run()
