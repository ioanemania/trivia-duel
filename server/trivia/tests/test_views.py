import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from redis_om import get_redis_connection
from rest_framework import status
from rest_framework.test import APITestCase

from core.settings import BASE_DIR
from trivia.models import Lobby, Game
from trivia.types import GameType, GameStatus

FIXTURES_PATH = BASE_DIR / "fixtures"

User = get_user_model()

test_db = get_redis_connection(url="redis://@redis:6379/1")
Lobby.Meta.database = test_db


class LobbyViewSetTestCase(APITestCase):
    fixtures = ["users.json"]

    @classmethod
    def setUpTestData(cls):
        cls.user1, cls.user2, cls.user3 = User.objects.all()[:3]
        cls.lobby_name = "TEST_LOBBY"

    def setUp(self):
        self.lobby = Lobby(name=self.lobby_name)
        self.lobby.save()

    def tearDown(self):
        for key in test_db.scan_iter("*"):
            test_db.delete(key)

    def test_create_lobby(self):
        url = reverse("lobby-list")
        lobby_name = "TEST_CREATE_LOBBY"

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(url, {"name": lobby_name}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        lobby = Lobby.get(lobby_name)
        expires_in = lobby.db().ttl(lobby.key())

        self.assertEqual(expires_in, settings.LOBBY_EXPIRE_SECONDS)
        self.assertEqual(lobby.name, lobby_name)
        self.assertIsNotNone(response.data.get("token"))

    def test_join_lobby_unauthenticated(self):
        url = reverse("lobby-join", args=[self.lobby_name])

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_join_lobby(self):
        url = reverse("lobby-join", args=[self.lobby_name])

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("token"))

    def test_join_lobby_non_existing(self):
        lobby_name = "NON_EXISTING_LOBBY"
        url = reverse("lobby-join", args=[lobby_name])

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_join_lobby_same_user_twice(self):
        url = reverse("lobby-join", args=[self.lobby_name])

        self.client.force_authenticate(user=self.user1)
        self.client.post(url)

        lobby = Lobby.get(self.lobby_name)
        lobby.users = {
            self.user1.id: {"name": self.user1.username, "hp": 100},
        }
        lobby.save()

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_join_lobby_two_users(self):
        url = reverse("lobby-join", args=[self.lobby_name])

        self.client.force_authenticate(user=self.user1)
        self.client.post(url)

        self.client.force_authenticate(user=self.user2)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_join_lobby_more_than_two_users(self):
        url = reverse("lobby-join", args=[self.lobby_name])

        self.client.force_authenticate(user=self.user1)
        self.client.post(url)

        self.client.force_authenticate(user=self.user2)
        self.client.post(url)

        lobby = Lobby.get(self.lobby_name)
        lobby.users = {
            self.user1.id: {"name": self.user1.username, "hp": 100},
            self.user2.id: {"name": self.user2.username, "hp": 100},
        }
        lobby.save()

        self.client.force_authenticate(user=self.user3)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_lobbies(self):
        url = reverse("lobby-list")

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), Lobby.find().count())

    def test_list_lobbies_ranked_filter(self):
        url = reverse("lobby-list") + "?ranked=True"

        Lobby(name="TEST_LOBBY_1", ranked=True).save()
        Lobby(name="TEST_LOBBY_2", ranked=False).save()

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), Lobby.find(Lobby.ranked == 1).count())

    def test_list_lobbies_normal_filter(self):
        url = reverse("lobby-list") + "?ranked=False"

        Lobby(name="TEST_LOBBY_1", ranked=True).save()
        Lobby(name="TEST_LOBBY_2", ranked=False).save()

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), Lobby.find(Lobby.ranked == 0).count())


class TrainingViewTestCase(APITestCase):
    fixtures = ["users.json"]

    @classmethod
    def setUpTestData(cls):
        cls.user1, cls.user2 = User.objects.all()[:2]

        with open(FIXTURES_PATH / "questions.json") as file:
            cls.questions = json.load(file)

    @patch("trivia.consumers.TriviaAPIClient.get_questions")
    def test_get_training_questions(self, mock_get_questions):
        mock_get_questions.return_value = self.questions

        url = reverse("train")

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, self.questions)

    def test_post_training_result(self):
        url = reverse("train")

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        games = self.user1.games.all()
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0].type, GameType.TRAINING)

    def test_get_history(self):
        url = reverse("history")

        game, user1_game, user2_game = Game.objects.save_multiplayer_game(
            game_type=GameType.RANKED,
            user1=self.user1,
            user2=self.user2,
            user1_status=GameStatus.WIN,
            user2_status=GameStatus.LOSS,
        )

        training_game, user1_training_game = Game.objects.save_training_game(user=self.user1)

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["game"]["type"], GameType.TRAINING.name.lower())
        self.assertEqual(response.data[1]["game"]["type"], GameType.RANKED.name.lower())
