from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class UserRegisterViewTestCase(APITestCase):
    def test_register_user(self):
        url = reverse("user-register")
        data = {"username": "user", "password": "user"}

        response = self.client.post(url, data=data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        User.objects.get(username=data["username"])


class UserRankingViewTestCase(APITestCase):
    fixtures = ["users.json"]

    @classmethod
    def setUpTestData(cls):
        cls.user1, cls.user2, cls.user3 = User.objects.all()[:3]

    def test_list_ranking(self):
        self.user1.rank = 1500
        self.user2.rank = 2000
        self.user3.rank = 1000

        self.user1.save()
        self.user2.save()
        self.user3.save()

        ordered_users = (self.user2.username, self.user1.username, self.user3.username)
        url = reverse("user-ranking")

        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTupleEqual(ordered_users, tuple(user["username"] for user in response.data))
