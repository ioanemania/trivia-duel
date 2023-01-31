import asyncio
import json
import secrets
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from redis_om import get_redis_connection

from trivia.urls import websocket_urlpatterns
from trivia.models import Lobby
from trivia.utils import generate_lobby_token_and_data

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures"

application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

User = get_user_model()
test_db = get_redis_connection(url="redis://@redis:6379/1")
Lobby.Meta.database = test_db


class GameConsumerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open(FIXTURES_PATH / "questions.json") as file:
            cls.questions = json.load(file)

        cls.lobby_name = "TEST_LOBBY_NAME"

    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", password="user1")
        self.user2 = User.objects.create_user(username="user2", password="user2")

        self.user1.save()
        self.user2.save()

        self.user1_token, user1_data = generate_lobby_token_and_data(self.user1)
        self.user2_token, user2_data = generate_lobby_token_and_data(self.user2)

        self.lobby = Lobby(name=self.lobby_name)
        self.lobby.users = {
            self.user1_token: user1_data,
            self.user2_token: user2_data
        }
        self.lobby.save()

    def tearDown(self):
        for key in test_db.scan_iter("*"):
            test_db.delete(key)

    async def test_unauthenticated_user_connect(self):
        comm = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}")
        connected, _ = await comm.connect()

        self.assertTrue(not connected)

    @patch("trivia.consumers.get_questions")
    async def test_two_users_connect(self, mock_get_questions):
        mock_get_questions.return_value = self.questions

        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        self.assertTrue(connected1)

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        self.assertTrue(connected2)

    @patch("trivia.consumers.get_questions")
    async def test_more_than_two_users_connect(self, mock_get_questions):
        mock_get_questions.return_value = self.questions

        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        comm3 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}")
        connected3, _ = await comm3.connect()

        self.assertTrue(not connected3)

        await comm2.disconnect()
        await comm1.disconnect()
