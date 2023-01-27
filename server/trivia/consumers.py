from channels.generic.websocket import JsonWebsocketConsumer
from channels.exceptions import DenyConnection
from asgiref.sync import async_to_sync
from redis_om.model.model import NotFoundError

from .models import Lobby


class GameConsumer(JsonWebsocketConsumer):
    def connect(self):
        self.lobby_name = self.scope["url_route"]["kwargs"]["lobby_name"]

        try:
            lobby = Lobby.get(self.lobby_name)
        except NotFoundError:
            raise DenyConnection()

        if len(lobby.users) > 1:
            raise DenyConnection()

        lobby.users.append(self.channel_name)
        lobby.save()

        async_to_sync(self.channel_layer.group_add)(self.lobby_name, self.channel_name)
        self.send_message_to_lobby(
            "player.joined",
            {
                "user": self.channel_name
            }
        )

        if len(lobby.users) == 2:
            pass  # start the game

    def disconnect(self, code):
        self.send_message_to_lobby(
            "player.left",
            {
                "user": self.channel_name
            }
        )

        lobby = Lobby.get(self.lobby_name)
        lobby.users.remove(self.channel_name)

        if len(lobby.users) == 0:
            Lobby.delete(lobby.pk)

        lobby.save()

        async_to_sync(self.channel_layer.group_discard)(self.lobby_name, self.channel_name)

    def send_message_to_lobby(self, msg_type: str, data: dict) -> None:
        async_to_sync(self.channel_layer.group_send)(
            self.lobby_name,
            {
                "type": msg_type,
                **data
            }
        )

    def player_joined(self, event):
        self.send_json(event)

    def player_left(self, event):
        self.send_json(event)
