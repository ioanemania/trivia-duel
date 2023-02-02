from typing import Optional, Iterable

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from channels.generic.websocket import JsonWebsocketConsumer
from channels.exceptions import DenyConnection, AcceptConnection
from redis_om.model.model import NotFoundError

from .models import Lobby, Game, LobbyState
from .types import GameEndEvent, UserId, HP, PlayerData, GameStatus
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
            self.send_event_to_lobby("game.start", {"questions": questions})

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
            self.send_game_end(
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

            if lobby.current_answer_count > 1:
                return

            if not content["correctly"]:
                lobby.users[self.token]["hp"] -= settings.QUESTION_DIFFICULTY_DAMAGE_MAP[content["difficulty"]]

            self.send_event_to_lobby(
                "opponent.answered",
                {"user_id": self.user_id, "correctly": content["correctly"]},
            )

            if lobby.current_answer_count == 1:
                if any(user for user in lobby.users.values() if user["hp"] <= 0):
                    self.send_game_end(self.determine_user_status_by_hp(list(lobby.users.values())))
                else:
                    lobby.current_answer_count = 0
                    self.send_event_to_lobby("question.next")
            else:
                lobby.current_answer_count += 1

            lobby.save()

    def send_event_to_lobby(self, msg_type: str, data: dict = None) -> None:
        if data is None:
            data = {}

        async_to_sync(self.channel_layer.group_send)(self.lobby_name, {"type": msg_type, **data})

    def send_game_end(self, users: dict[UserId, GameStatus]):
        self.send_event_to_lobby("game.end", {"users": users})

    def game_start(self, event: dict):
        self.send_json(event)

    def game_end(self, event: GameEndEvent):
        lobby = Lobby.get(self.lobby_name)

        player_status = event["users"][self.user_id]

        match player_status:
            case GameStatus.WIN:
                rank_gain = 20
            case GameStatus.LOSS:
                rank_gain = -20
            case GameStatus.DRAW:
                rank_gain = 0
            case _:
                raise Exception("Undefined Status")

        user = User.objects.get(pk=self.user_id)
        if lobby.ranked:
            user.rank += rank_gain
            user.save()

        game = Game(
            user=user,
            rank=user.rank,
            status=player_status.name.lower(),
            # TODO: Use choices
            type="ranked" if lobby.ranked else "casual",
        )
        game.save()

        self.send_json(
            {
                "type": event["type"],
                "status": player_status.name.lower(),
                "rank_gain": rank_gain,
            }
        )

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
