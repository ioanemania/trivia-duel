import secrets

from django.test import TestCase
from django.contrib.auth import get_user_model

from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async

from .urls import websocket_urlpatterns
from .models import Lobby

application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

User = get_user_model()


class GameConsumerTestCase(TestCase):
    async def test_unauthenticated_user_connect(self):
        lobby_name = "TEST_LOBBY_NAME"

        Lobby(name=lobby_name).save()

        comm = WebsocketCommunicator(application, f"/lobbies/{lobby_name}")
        connected, _ = await comm.connect()

        self.assertTrue(not connected)

    async def test_more_than_two_users_connect(self):
        lobby_name = "TEST_LOBBY_NAME"
        user1 = await database_sync_to_async(User.objects.create_user)(username="user1", password="user1")
        await database_sync_to_async(user1.save)()
        user1_token_tuple = (secrets.token_urlsafe(16), user1.id)

        user2 = await database_sync_to_async(User.objects.create_user)(username="user2", password="user2")
        await database_sync_to_async(user2.save)()
        user2_token_tuple = (secrets.token_urlsafe(16), user2.id)

        Lobby(name=lobby_name, tokens=[user1_token_tuple, user2_token_tuple]).save()

        comm1 = WebsocketCommunicator(application, f"/lobbies/{lobby_name}?{user1_token_tuple[0]}")
        connected1, _ = await comm1.connect()

        self.assertTrue(connected1)

        comm2 = WebsocketCommunicator(application, f"/lobbies/{lobby_name}?{user2_token_tuple[0]}")
        connected2, _ = await comm2.connect()

        self.assertTrue(connected2)

        comm3 = WebsocketCommunicator(application, f"/lobbies/{lobby_name}")
        connected3, _ = await comm3.connect()

        self.assertTrue(not connected3)

        await comm2.disconnect()
        await comm1.disconnect()
