import json
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from trivia.utils import TriviaAPIClient

FIXTURES_PATH = settings.BASE_DIR / "fixtures"


class TriviaAPIClientTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        with open(FIXTURES_PATH / "questions.json") as file:
            cls.questions = json.load(file)

    def setUp(self) -> None:
        self.requests_patcher = patch("trivia.utils.requests")
        self.mock_requests = self.requests_patcher.start()

    def tearDown(self) -> None:
        self.mock_requests.stop()

    def test_get_questions_without_token(self):
        url = settings.TRIVIA_API_URL

        mock_response = self.mock_requests.get.return_value
        mock_response.json.return_value = {"results": self.questions}

        questions = TriviaAPIClient.get_questions()

        self.mock_requests.get.assert_called_once_with(url)
        self.assertEqual(questions, self.questions)

    def test_get_questions_with_token(self):
        token = "RANDOM_TOKEN"
        url = settings.TRIVIA_API_URL + f"&token={token}"

        mock_response = self.mock_requests.get.return_value
        mock_response.json.return_value = {"results": self.questions}

        questions = TriviaAPIClient.get_questions(token)

        self.mock_requests.get.assert_called_once_with(url)
        self.assertEqual(questions, self.questions)

    def test_get_token(self):
        token = "RANDOM_TOKEN"

        mock_response = self.mock_requests.get.return_value
        mock_response.json.return_value = {"token": token}

        received_token = TriviaAPIClient.get_token()

        self.mock_requests.get.assert_called_once_with(settings.TRIVIA_API_TOKEN_URL)
        self.assertEqual(received_token, token)
