from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

User = get_user_model()


class RegisterUserViewTestCase(APITestCase):
    def test_register_user(self):
        url = reverse("user-register")
        data = {"username": "user", "password": "user"}

        response = self.client.post(url, data=data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        User.objects.get(username=data["username"])
