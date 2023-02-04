from typing import Optional

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from channels.generic.websocket import JsonWebsocketConsumer
from channels.exceptions import DenyConnection, AcceptConnection
from redis_om.model.model import NotFoundError

from .models import Lobby, Game, LobbyState, UserGame
from .types import GameEndEvent, UserId, PlayerData, GameStatus, UserStatus, GameType
from .utils import get_questions

User = get_user_model()


class GameConsumer(JsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        self.lobby_name: Optional[str] = None
        self.token: Optional[str] = None
        self.user_id: Optional[int] = None

        super().__init__(*args, **kwargs)

    def get_token_from_query_string(self) -> str:
        return self.scope["query_string"].decode()

    def connect(self):
        # TODO: Error handling
        self.lobby_name = self.scope["url_route"]["kwargs"]["lobby_name"]

        try:
            lobby = Lobby.get(self.lobby_name)
        except NotFoundError:
            raise DenyConnection()

        if lobby.user_count > 1:
            raise DenyConnection()

        self.token = self.get_token_from_query_string()
        if not lobby.users.get(self.token):
            raise DenyConnection()

        lobby.user_count += 1

        self.user_id = lobby.users.get(self.token)["user_id"]

        async_to_sync(self.channel_layer.group_add)(self.lobby_name, self.channel_name)

        if lobby.user_count == 2:
            questions = get_questions()
            lobby.state = LobbyState.IN_PROGRESS
            self.send_event_to_lobby("question.data", {"questions": questions})
            self.send_event_to_lobby("game.start")

        lobby.save()

        raise AcceptConnection()

    def disconnect(self, code):
        lobby = Lobby.get(self.lobby_name)
        lobby.user_count -= 1

        # If both users have disconnected, the lobby is deleted.
        if lobby.user_count == 0:
            Lobby.delete(lobby.name)
            async_to_sync(self.channel_layer.group_discard)(self.lobby_name, self.channel_name)
            return

        async_to_sync(self.channel_layer.group_discard)(self.lobby_name, self.channel_name)

        # If one of the users disconnected, but the game was still in progress declare the in game user a winner
        if lobby.state == LobbyState.IN_PROGRESS:
            opponent_user_id = next(user["user_id"] for user in lobby.users.values() if user["user_id"] != self.user_id)
            self.handle_game_end(
                {
                    self.user_id: GameStatus.LOSS,
                    opponent_user_id: GameStatus.WIN,
                }
            )

        del lobby.users[self.token]
        lobby.save()

    def receive_json(self, content: dict, **kwargs):
        if content["type"] == "question.answered":
            lobby = Lobby.get(self.lobby_name)

            # receiving question.answered event more than two times for a single question is unexpected, ignore it
            if lobby.current_answer_count > 1:
                return

            if not content["correctly"]:
                lobby.users[self.token]["hp"] -= settings.QUESTION_DIFFICULTY_DAMAGE_MAP[content["difficulty"]]

            self.send_event_to_lobby(
                "opponent.answered",
                {"user_id": self.user_id, "correctly": content["correctly"]},
            )

            # question has been answered for the first time
            if lobby.current_answer_count == 0:
                lobby.current_answer_count += 1
                lobby.save()
                return

            # otherwise, both users have answered the question
            if any(user for user in lobby.users.values() if user["hp"] <= 0):
                self.handle_game_end(self.determine_user_status_by_hp(list(lobby.users.values())))
                return

            # current set of questions has been exhausted, obtain new ones
            if lobby.current_question_count == 8:  # TODO: refactor hardcoded value
                lobby.current_question_count = 0

                questions = get_questions()
                self.send_event_to_lobby("question.data", {"questions": questions})
            else:
                lobby.current_question_count += 1

            lobby.current_answer_count = 0
            lobby.save()

            self.send_event_to_lobby("question.next")

    def send_event_to_lobby(self, msg_type: str, data: dict = None) -> None:
        if data is None:
            data = {}

        async_to_sync(self.channel_layer.group_send)(self.lobby_name, {"type": msg_type, **data})

    def handle_game_end(self, users: dict[UserId, GameStatus]) -> None:
        lobby = Lobby.get(self.lobby_name)
        lobby.state = LobbyState.FINISHED
        lobby.save()

        game = Game(
            type=GameType.RANKED if lobby.ranked else GameType.NORMAL,
        )
        game.save()

        user_status_dict: dict[UserId, UserStatus] = {}
        user_objects = User.objects.filter(pk__in=(users.keys()))
        for user in user_objects:
            status = users[user.pk]
            rank_gain = self.determine_rank_gain_by_game_status(status)
            if lobby.ranked:
                user.rank = max(user.rank + rank_gain, 0)
                user.save()

            UserGame(
                user=user,
                game=game,
                status=status,
                rank=user.rank,
            ).save()

            user_status_dict[user.pk] = {"status": status, "rank_gain": rank_gain}

        self.send_event_to_lobby("game.end", {"users": user_status_dict})

    def game_start(self, event: dict):
        self.send_json(event)

    def game_end(self, event: GameEndEvent):
        user_status = event["users"][self.user_id]

        self.send_json(
            {"type": event["type"], "status": user_status["status"].name.lower(), "rank_gain": user_status["rank_gain"]}
        )

    def question_data(self, event: dict):
        self.send_json(event)

    def question_next(self, event: dict):
        self.send_json(event)

    def opponent_answered(self, event: dict):
        if not event["user_id"] == self.user_id:
            self.send_json(event)

    def determine_user_status_by_hp(self, users: list[PlayerData]) -> dict[UserId, GameStatus]:  # noqa
        """Determine the win/loss/draw status of both users based on their hp"""

        user1_id, user1_hp = users[0]["user_id"], users[0]["hp"]
        user2_id, user2_hp = users[1]["user_id"], users[1]["hp"]

        if user1_hp == user2_hp:
            user1_status = user2_status = GameStatus.DRAW
        elif user1_hp > user2_hp:
            user1_status, user2_status = GameStatus.WIN, GameStatus.LOSS
        else:
            user1_status, user2_status = GameStatus.LOSS, GameStatus.WIN

        return {
            user1_id: user1_status,
            user2_id: user2_status,
        }

    def determine_rank_gain_by_game_status(self, status: GameStatus) -> int:  # noqa
        match status:
            case GameStatus.WIN:
                return 20
            case GameStatus.LOSS:
                return -20
            case GameStatus.DRAW:
                return 0
            case _:
                raise Exception("Undefined Status")
