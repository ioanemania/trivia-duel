from typing import Optional

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from channels.generic.websocket import JsonWebsocketConsumer
from channels.exceptions import DenyConnection, AcceptConnection
from redis_om.model.model import NotFoundError

from .models import Lobby, Game
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
        lobby.save()

        self.user_id = lobby.users.get(self.token)["user_id"]

        async_to_sync(self.channel_layer.group_add)(self.lobby_name, self.channel_name)

        if lobby.user_count == 2:
            questions = get_questions()
            self.send_event_to_lobby("game.start", {"questions": questions})

        raise AcceptConnection()

    def disconnect(self, code):
        lobby = Lobby.get(self.lobby_name)
        del lobby.users[self.token]
        lobby.user_count -= 1

        if lobby.user_count == 0:
            Lobby.delete(lobby.name)
        else:
            lobby.save()

        async_to_sync(self.channel_layer.group_discard)(self.lobby_name, self.channel_name)

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
                    self.send_event_to_lobby("game.end")
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

    def game_start(self, event: dict):
        self.send_json(event)

    def game_end(self, event: dict):
        lobby = Lobby.get(self.lobby_name)

        player_hp = lobby.users[self.token]["hp"]
        opponent_hp = None

        for token in lobby.users.keys():
            if token != self.token:
                opponent_hp = lobby.users[token]["hp"]
                break

        if player_hp == opponent_hp:
            status = "draw"
            rank_gain = 0
        elif player_hp > opponent_hp:
            status = "win"
            rank_gain = 20
        else:
            status = "loss"
            rank_gain = -20

        user = User.objects.get(pk=self.user_id)
        if lobby.ranked:
            user.rank += rank_gain
            user.save()

        game = Game(
            user=user,
            rank=user.rank,
            status=status,
            # TODO: Use choices
            type="ranked" if lobby.ranked else "casual",
        )
        game.save()

        event.update({"status": status, "rank_gain": rank_gain})
        self.send_json(event)

    def question_next(self, event: dict):
        self.send_json(event)

    def opponent_answered(self, event: dict):
        if not event["user_id"] == self.user_id:
            self.send_json(event)
