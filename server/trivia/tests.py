from django.test import TestCase

from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack

from .urls import websocket_urlpatterns
from .models import Lobby

application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))


class GameConsumerTestCase(TestCase):
    async def test_more_than_two_users_connect(self):
        lobby_name = "TEST_LOBBY_NAME"

        Lobby(name=lobby_name).save()

        comm1 = WebsocketCommunicator(application, f"/lobbies/{lobby_name}")
        connected1, _ = await comm1.connect()

        self.assertTrue(connected1)

        comm2 = WebsocketCommunicator(application, f"/lobbies/{lobby_name}")
        connected2, _ = await comm2.connect()

        self.assertTrue(connected2)

        comm3 = WebsocketCommunicator(application, f"/lobbies/{lobby_name}")
        connected3, _ = await comm3.connect()

        self.assertTrue(not connected3)

        await comm2.disconnect()
        await comm1.disconnect()
