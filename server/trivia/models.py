from datetime import datetime
from typing import Dict

from django.contrib.auth import get_user_model
from django.db import models
from redis_om import Field, JsonModel, Migrator
from trivia.types import (
    CorrectAnswer,
    GameStatus,
    GameType,
    LobbyState,
    PlayerData,
    UserId,
)

User = get_user_model()


class Lobby(JsonModel):
    name: str = Field(primary_key=True)
    ready_count: int = 0
    users: Dict[UserId, PlayerData] = {}
    current_answer_count: int = 0
    current_question_count: int = 0
    state: LobbyState = LobbyState.WAITING
    ranked: int = Field(index=True, default=0)
    trivia_token: str = ""
    correct_answers: list[CorrectAnswer] = []
    game_start_time: datetime = 0
    question_start_time: datetime = 0


class Game(models.Model):
    type = models.IntegerField(choices=GameType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    players = models.ManyToManyField(User, through="UserGame", through_fields=("game", "user"), related_name="games")

    class GameManager(models.Manager):
        def save_multiplayer_game(
            self, game_type: GameType, user1: User, user2: User, user1_status: GameStatus, user2_status: GameStatus
        ) -> tuple["Game", "UserGame", "UserGame"]:
            """
            Creates and saves a new Game and associated UserGame records/objects in the database.

            Returns:
                Tuple of the created Game and UserGame objects

            """
            if game_type == GameType.TRAINING:
                raise Exception(
                    f"Trying to use {self.create_multiplayer_game.__name__} to create a record of a training game,"
                    f" you should probably use {self.create_training_game.__name__} instead."
                )

            game = Game(type=game_type)
            game.save()

            user1_game = UserGame(user=user1, opponent=user2, game=game, status=user1_status, rank=user1.rank)
            user2_game = UserGame(user=user2, opponent=user1, game=game, status=user2_status, rank=user2.rank)

            user1_game.save()
            user2_game.save()

            return game, user1_game, user2_game

        def save_training_game(self, user: User) -> tuple["Game", "UserGame"]:
            """
            Creates and saves a new training Game and associated UserGame records in the database.

            Returns:

            """
            game = Game(type=GameType.TRAINING)
            game.save()

            user1_game = UserGame(user=user, game=game, status=GameStatus.WIN, rank=user.rank)
            user1_game.save()

            return game, user1_game

    objects = GameManager()


class UserGame(models.Model):
    user = models.ForeignKey(User, related_name="user_games", on_delete=models.CASCADE)
    opponent = models.ForeignKey(User, related_name="opponent_user_games", null=True, on_delete=models.SET_NULL)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    status = models.IntegerField(choices=GameStatus.choices)
    rank = models.PositiveIntegerField()
    extra_data = models.JSONField(null=True)


Migrator().run()  # TODO: Move this statement
