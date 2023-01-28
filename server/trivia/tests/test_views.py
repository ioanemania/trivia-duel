from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from redis_om import get_redis_connection

from trivia.models import Lobby

User = get_user_model()

test_db = get_redis_connection(url="redis://@redis:6379/1")
Lobby.Meta.database = test_db


class LobbyViewSetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create_user(username="user1", password="user1")
        cls.user1.save()
        cls.user2 = User.objects.create_user(username="user2", password="user2")
        cls.user2.save()
        cls.user3 = User.objects.create_user(username="user3", password="user3")
        cls.user3.save()

    def tearDown(self) -> None:
        for key in test_db.scan_iter("*"):
            test_db.delete(key)

    def test_create_lobby(self):
        url = reverse("lobby-list")
        lobby_name = "TEST_LOBBY"

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(url, {"name": lobby_name}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Lobby.get(lobby_name).name, lobby_name)

    def test_join_lobby_unauthenticated(self):
        lobby_name = "TEST_LOBBY"
        lobby = Lobby(name=lobby_name)
        lobby.save()
        url = reverse("lobby-join", args=[lobby_name])

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_join_lobby(self):
        lobby_name = "TEST_LOBBY"
        lobby = Lobby(name=lobby_name)
        lobby.save()
        url = reverse("lobby-join", args=[lobby_name])

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data['token']
        lobby = Lobby.get(lobby_name)
        self.assertIn(token, (token_tuple[0] for token_tuple in lobby.tokens))

    def test_join_lobby_non_existing(self):
        lobby_name = "TEST_LOBBY"
        url = reverse("lobby-join", args=[lobby_name])

        self.client.force_authenticate(user=self.user1)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_join_lobby_same_user_twice(self):
        lobby_name = "TEST_LOBBY"
        lobby = Lobby(name=lobby_name)
        lobby.save()
        url = reverse("lobby-join", args=[lobby_name])

        self.client.force_authenticate(user=self.user1)
        self.client.post(url)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_join_lobby_two_users(self):
        lobby_name = "TEST_LOBBY"
        lobby = Lobby(name=lobby_name)
        lobby.save()
        url = reverse("lobby-join", args=[lobby_name])

        self.client.force_authenticate(user=self.user1)
        self.client.post(url)

        self.client.force_authenticate(user=self.user2)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_join_lobby_more_than_two_users(self):
        lobby_name = "TEST_LOBBY"
        lobby = Lobby(name=lobby_name)
        lobby.save()
        url = reverse("lobby-join", args=[lobby_name])

        self.client.force_authenticate(user=self.user1)
        self.client.post(url)

        self.client.force_authenticate(user=self.user2)
        self.client.post(url)

        self.client.force_authenticate(user=self.user3)
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
