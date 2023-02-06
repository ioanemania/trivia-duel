import json
from pathlib import Path
from unittest.mock import patch

from channels.db import database_sync_to_async
from django.test import TestCase
from django.contrib.auth import get_user_model

from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from redis_om import get_redis_connection

from core.settings import BASE_DIR
from trivia.urls import websocket_urlpatterns
from trivia.models import Lobby, UserGame
from trivia.utils import generate_lobby_token_and_data
from trivia.types import GameStatus

FIXTURES_PATH = BASE_DIR / "fixtures"

application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

User = get_user_model()
test_db = get_redis_connection(url="redis://@redis:6379/1")
Lobby.Meta.database = test_db


class GameConsumerTestCase(TestCase):
    fixtures = ["users.json"]

    @classmethod
    def setUpTestData(cls):
        with open(FIXTURES_PATH / "questions.json") as file:
            cls.questions = json.load(file)

        cls.lobby_name = "TEST_LOBBY_NAME"

    def setUp(self):
        self.user1, self.user2 = User.objects.all()[:2]

        self.user1_token, user1_data = generate_lobby_token_and_data(self.user1)
        self.user2_token, user2_data = generate_lobby_token_and_data(self.user2)

        lobby = Lobby(name=self.lobby_name, ranked=1)
        lobby.users = {self.user1_token: user1_data, self.user2_token: user2_data}
        lobby.save()

        self.get_questions_patcher = patch("trivia.consumers.TriviaAPIClient.get_questions")
        self.get_token_patcher = patch("trivia.consumers.TriviaAPIClient.get_token")

        self.mock_get_questions = self.get_questions_patcher.start()
        self.mock_get_token = self.get_token_patcher.start()

        self.mock_get_questions.return_value = self.questions
        self.mock_get_token.return_value = "FAKE_TOKEN"

    def tearDown(self):
        self.get_questions_patcher.stop()
        self.get_token_patcher.stop()

        for key in test_db.scan_iter("*"):
            test_db.delete(key)

    async def test_unauthenticated_user_connect(self):
        comm = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}")
        connected, _ = await comm.connect()

        self.assertTrue(not connected)

    async def test_two_users_connect(self):
        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        self.assertTrue(connected1)

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        self.assertTrue(connected2)

    async def test_more_than_two_users_connect(self):
        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        comm3 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}")
        connected3, _ = await comm3.connect()

        self.assertTrue(not connected3)

        await comm2.disconnect()
        await comm1.disconnect()

    async def test_user_disconnects_when_game_in_progress(self):
        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        await comm1.disconnect()

        await comm2.receive_json_from()  # game.start
        await comm2.receive_json_from()  # question.data
        await comm2.receive_json_from()  # question.next
        comm2_game_end = await comm2.receive_json_from()  # game.end

        self.assertEqual(comm2_game_end["status"], GameStatus.WIN.name.lower())

        await comm2.disconnect()

    async def test_questions_are_continuously_obtained(self):
        data = {"type": "question.answered", "correctly": True, "difficulty": "hard"}

        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        await comm1.receive_json_from()  # game.start
        await comm1.receive_json_from()  # game.data
        await comm1.receive_json_from()  # game.next

        await comm2.receive_json_from()  # game.start
        await comm2.receive_json_from()  # game.data
        await comm2.receive_json_from()  # game.next

        for i in range(10):  # TODO: refactor hardcoded value
            await comm1.send_json_to(data)
            await comm2.send_json_to(data)

            await comm1.receive_json_from()
            await comm2.receive_json_from()

        self.assertEqual(self.mock_get_questions.call_count, 2)

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_game_data_is_stored(self):
        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        # don't simulate the whole game, just disconnect the first user
        # so the game ends and the second user is declared a winner
        await comm1.disconnect()

        await comm2.receive_json_from()  # game.start
        await comm2.receive_json_from()  # question.data
        await comm2.receive_json_from()  # question.next
        await comm2.receive_json_from()  # game.end
        await comm2.disconnect()

        user1_games_played = self.user1.games.all()
        user2_games_played = self.user2.games.all()

        self.assertEqual(await database_sync_to_async(len)(user1_games_played), 1)
        self.assertEqual(await database_sync_to_async(len)(user2_games_played), 1)
        self.assertEqual(user1_games_played[0], user2_games_played[0])

        user1_user_game_record = await database_sync_to_async(UserGame.objects.get)(
            user=self.user1, game=user1_games_played[0]
        )
        user2_user_game_record = await database_sync_to_async(UserGame.objects.get)(
            user=self.user2, game=user2_games_played[0]
        )

        self.assertEqual(user1_user_game_record.status, GameStatus.LOSS.value)
        self.assertEqual(user2_user_game_record.status, GameStatus.WIN.value)

    async def test_ranks_updating_correctly(self):
        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        user1_prev_rank = self.user1.rank
        user2_prev_rank = self.user2.rank

        await comm1.receive_json_from()  # game.start
        await comm1.receive_json_from()  # question.data
        await comm1.receive_json_from()  # question.next

        await comm2.receive_json_from()  # game.start
        await comm2.receive_json_from()  # question.data
        await comm2.receive_json_from()  # question.next

        lobby = Lobby.get(self.lobby_name)
        lobby.users[self.user1_token]["hp"] = 0
        lobby.save()

        await comm1.send_json_to({"type": "question.answered", "correctly": False, "difficulty": "easy"})

        await comm2.send_json_to({"type": "question.answered", "correctly": False, "difficulty": "easy"})

        await comm1.receive_json_from()  # opponent.answered
        await comm2.receive_json_from()  # opponent.answered

        await comm1.receive_json_from()  # opponent.answered
        await comm2.receive_json_from()  # opponent.answered

        await comm1.disconnect()
        await comm2.disconnect()

        await database_sync_to_async(self.user1.refresh_from_db)()
        await database_sync_to_async(self.user2.refresh_from_db)()

        self.assertEqual(self.user1.rank, user1_prev_rank - 20)  # TODO: Remove hardcoded value
        self.assertEqual(self.user2.rank, user2_prev_rank + 20)  # TODO: Remove hardcoded value

    async def test_server_initial_event_sequence(self):
        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        event1 = await comm1.receive_json_from()  # game.start
        event2 = await comm1.receive_json_from()  # question.data
        event3 = await comm1.receive_json_from()  # question.next

        await comm1.disconnect()
        await comm2.disconnect()

        self.assertEqual(event1["type"], "game.start")
        self.assertEqual(event2["type"], "question.data")
        self.assertEqual(event3["type"], "question.next")

    async def test_game_timout_received(self):
        comm1 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user1_token}")
        connected1, _ = await comm1.connect()

        comm2 = WebsocketCommunicator(application, f"/lobbies/{self.lobby_name}?{self.user2_token}")
        connected2, _ = await comm2.connect()

        await comm1.receive_json_from()  # game.start
        await comm1.receive_json_from()  # question.data
        await comm1.receive_json_from()  # question.next

        await comm2.receive_json_from()  # game.start
        await comm2.receive_json_from()  # question.data
        await comm2.receive_json_from()  # question.next

        await comm1.send_json_to({"type": "game.timeout"})

        await comm1.send_json_to({"type": "question.answered", "correctly": False, "difficulty": "easy"})
        await comm2.send_json_to({"type": "question.answered", "correctly": True, "difficulty": "easy"})

        await comm1.receive_json_from()  # opponent.answered
        await comm2.receive_json_from()  # opponent.answered

        comm1_game_end = await comm1.receive_json_from()  # game.end
        comm2_game_end = await comm2.receive_json_from()  # game.end

        self.assertEqual(comm1_game_end["type"], "game.end")
        self.assertEqual(comm1_game_end["status"], GameStatus.LOSS.name.lower())

        self.assertEqual(comm2_game_end["type"], "game.end")
        self.assertEqual(comm2_game_end["status"], GameStatus.WIN.name.lower())
