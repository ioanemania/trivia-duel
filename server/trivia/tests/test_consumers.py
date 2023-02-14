import html
import json
from datetime import datetime, timedelta
from unittest.mock import ANY, MagicMock, call, patch

from channels.auth import AuthMiddlewareStack
from channels.exceptions import AcceptConnection, DenyConnection
from channels.routing import URLRouter
from core.settings.base import BASE_DIR
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from redis_om import get_redis_connection
from redis_om.model.model import NotFoundError
from trivia.consumers import GameConsumer
from trivia.models import Game, Lobby, UserGame
from trivia.types import (
    ClientEvent,
    CorrectAnswer,
    FiftyRequestedEvent,
    GameEndEvent,
    GameStatus,
    GameType,
    LobbyState,
    QuestionAnsweredEvent,
    TriviaAPIQuestion,
)
from trivia.urls import websocket_urlpatterns
from trivia.utils import generate_lobby_token

FIXTURES_PATH = BASE_DIR / "fixtures"

application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))

User = get_user_model()
redis = get_redis_connection()


class GameConsumerTestCase(TestCase):
    fixtures = ["users.json"]

    @classmethod
    def setUpTestData(cls):
        with open(FIXTURES_PATH / "questions.json") as file:
            cls.questions = json.load(file)

        cls.lobby_name = "TEST_LOBBY_NAME"

    def setUp(self):
        self.user1, self.user2 = User.objects.all()[:2]

        self.user1_token = generate_lobby_token(self.user1, self.lobby_name)
        self.user2_token = generate_lobby_token(self.user2, self.lobby_name)

        lobby = Lobby(name=self.lobby_name, ranked=1)
        lobby.users = {
            self.user1.id: {
                "name": self.user1.username,
                "hp": 100,
            },
            self.user2.id: {
                "name": self.user2.username,
                "hp": 100,
            },
        }
        lobby.save()

        self.get_questions_patcher = patch("trivia.consumers.TriviaAPIClient.get_questions")
        self.get_token_patcher = patch("trivia.consumers.TriviaAPIClient.get_token")
        self.send_event_to_lobby_patcher = patch("trivia.consumers.GameConsumer.send_event_to_lobby")

        self.mock_get_questions = self.get_questions_patcher.start()
        self.mock_get_token = self.get_token_patcher.start()
        self.mock_send_event_to_lobby = self.send_event_to_lobby_patcher.start()

        self.mock_get_questions.return_value = self.questions
        self.mock_get_token.return_value = "FAKE_TOKEN"

        self.game_consumer = GameConsumer()
        self.game_consumer.scope = {"query_string": b"", "url_route": {"kwargs": {"lobby_name": self.lobby_name}}}
        self.game_consumer.lobby_name = self.lobby_name
        self.game_consumer.channel_layer = MagicMock()
        self.game_consumer.channel_name = MagicMock()

        self.formatted_questions, self.correct_answers = self.game_consumer.get_and_format_questions("FAKE_TOKEN")

    def tearDown(self):
        self.get_questions_patcher.stop()
        self.get_token_patcher.stop()
        self.send_event_to_lobby_patcher.stop()

        for key in redis.scan_iter("*"):
            redis.delete(key)

    def test_unauthenticated_user_connect(self):
        lobby = Lobby.get(self.lobby_name)
        lobby.users = {}
        lobby.save()

        with self.assertRaises(DenyConnection):
            self.game_consumer.connect()

    def test_authenticated_user_with_token_for_wrong_lobby_connect(self):
        self.game_consumer.scope["query_string"] = generate_lobby_token(self.user1, "SOME_OTHER_LOBBY").encode()

        lobby = Lobby.get(self.lobby_name)
        lobby.users = {}
        lobby.save()

        with self.assertRaises(DenyConnection):
            self.game_consumer.connect()

    @patch("trivia.consumers.async_to_sync")
    def test_authenticated_user_connect(self, mock_async_to_sync: MagicMock):
        self.game_consumer.scope["query_string"] = self.user1_token.encode()

        lobby = Lobby.get(self.lobby_name)
        lobby.users = {}
        lobby.save()

        with self.assertRaises(AcceptConnection):
            self.game_consumer.connect()

        mock_async_to_sync.assert_called_once_with(self.game_consumer.channel_layer.group_add)

    def test_user_connect_to_invalid_lobby(self):
        self.game_consumer.scope["url_route"]["kwargs"]["lobby_name"] = "INVALID_LOBBY_NAME"

        with self.assertRaises(DenyConnection):
            self.game_consumer.connect()

    @patch("trivia.consumers.async_to_sync")
    def test_second_user_connect(self, mock_async_to_sync: MagicMock):
        self.game_consumer.scope["query_string"] = self.user2_token.encode()

        lobby = Lobby.get(self.lobby_name)
        del lobby.users[self.user2.id]
        lobby.save()

        with self.assertRaises(AcceptConnection):
            self.game_consumer.connect()

        mock_async_to_sync.assert_called_once_with(self.game_consumer.channel_layer.group_add)
        self.mock_send_event_to_lobby.assert_called_once_with("game.prepare")

    def test_more_than_two_users_connect(self):
        user3 = User.objects.all()[2]
        self.game_consumer.scope["query_string"] = generate_lobby_token(user3, self.lobby_name)

        with self.assertRaises(DenyConnection):
            self.game_consumer.connect()

    def test_same_user_connect_second_time(self):
        self.game_consumer.scope["query_string"] = self.user1_token.encode()

        lobby = Lobby.get(self.lobby_name)
        del lobby.users[self.user2.id]
        lobby.save()

        with self.assertRaises(DenyConnection):
            self.game_consumer.connect()

    @patch("trivia.consumers.async_to_sync")
    def test_unauthenticated_user_disconnect(self, mock_async_to_sync: MagicMock):
        expected_lobby = Lobby.get(self.lobby_name)

        self.game_consumer.disconnect(1006)

        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        mock_async_to_sync.assert_not_called()

    @patch("trivia.consumers.async_to_sync")
    def test_last_user_disconnect(self, mock_async_to_sync: MagicMock):
        lobby = Lobby.get(self.lobby_name)
        del lobby.users[self.user2.id]
        lobby.save()
        self.game_consumer.user_id = self.user1.id

        self.game_consumer.disconnect(1000)

        mock_async_to_sync.assert_called_once_with(self.game_consumer.channel_layer.group_discard)
        with self.assertRaises(NotFoundError):
            Lobby.get(self.lobby_name)

    @patch("trivia.consumers.async_to_sync")
    def test_first_user_disconnect(self, mock_async_to_sync: MagicMock):
        self.game_consumer.user_id = self.user2.id

        self.game_consumer.disconnect(1000)

        mock_async_to_sync.assert_called_once_with(self.game_consumer.channel_layer.group_discard)
        lobby = Lobby.get(self.lobby_name)
        self.assertIsNone(lobby.users.get(self.user2.id))

    @patch("trivia.consumers.GameConsumer.handle_game_end")
    @patch("trivia.consumers.async_to_sync")
    def test_user_disconnect_when_game_in_progress(
        self, mock_async_to_sync: MagicMock, mock_handle_game_end: MagicMock
    ):
        self.game_consumer.user_id = self.user1.id

        lobby = Lobby.get(self.lobby_name)
        lobby.state = LobbyState.IN_PROGRESS
        lobby.save()

        self.game_consumer.disconnect(1000)

        mock_async_to_sync.assert_called_once_with(self.game_consumer.channel_layer.group_discard)
        mock_handle_game_end.assert_called_once_with({self.user1.id: GameStatus.LOSS, self.user2.id: GameStatus.WIN})

    def test_receive_game_ready_only_one_user_in_lobby(self):
        lobby = Lobby.get(self.lobby_name)
        del lobby.users[self.user2.id]
        lobby.save()

        expected_lobby = lobby

        content: ClientEvent = {"type": "game.ready"}

        self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)
        self.assertEqual(expected_lobby, lobby_after_call)
        self.mock_send_event_to_lobby.assert_not_called()

    def test_receive_game_ready_first_user(self):
        expected_lobby = Lobby.get(self.lobby_name)
        expected_lobby.ready_count = 1

        content: ClientEvent = {"type": "game.ready"}

        self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertTrue(self.game_consumer.ready_sent)
        self.assertEqual(expected_lobby, lobby_after_call)
        self.mock_send_event_to_lobby.assert_not_called()

    def test_receive_game_ready_second_time_by_same_user(self):
        self.game_consumer.ready_sent = True

        lobby = Lobby.get(self.lobby_name)
        lobby.ready_count = 1
        lobby.save()

        expected_lobby = lobby

        content: ClientEvent = {"type": "game.ready"}

        self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.mock_send_event_to_lobby.assert_not_called()

    @patch("trivia.consumers.datetime")
    def test_receive_game_ready_second_user(self, mock_datetime):
        mock_datetime.now.return_value = datetime.now()

        lobby = Lobby.get(self.lobby_name)
        lobby.ready_count = 1
        lobby.save()

        expected_lobby = lobby
        expected_lobby.ready_count = 2
        expected_lobby.trivia_token = self.mock_get_token.return_value
        expected_lobby.state = LobbyState.IN_PROGRESS
        expected_lobby.game_start_time = mock_datetime.now.return_value
        expected_lobby.question_start_time = mock_datetime.now.return_value
        expected_lobby.correct_answers = self.correct_answers

        content: ClientEvent = {"type": "game.ready"}

        with patch("trivia.consumers.GameConsumer.get_and_format_questions") as mock_get_and_format_questions:
            mock_get_and_format_questions.return_value = (self.formatted_questions, self.correct_answers)
            self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertTrue(self.game_consumer.ready_sent)
        self.assertEqual(expected_lobby, lobby_after_call)
        self.mock_send_event_to_lobby.assert_has_calls(
            (
                call(
                    "game.start",
                    {
                        "users": {str(self.user1.id): self.user2.username, str(self.user2.id): self.user1.username},
                        "duration": settings.GAME_MAX_DURATION_SECONDS,
                    },
                ),
                call("question.data", {"questions": self.formatted_questions}),
                call("question.next"),
            ),
            any_order=False,
        )

    def test_receive_question_answered_more_than_once_by_same_user(self):
        lobby = Lobby.get(self.lobby_name)
        lobby.current_answer_count = 1
        lobby.save()

        expected_lobby = lobby

        content: QuestionAnsweredEvent = {"type": "question.answered", "answer": "RANDOM_ANSWER"}
        self.game_consumer.question_answered = True

        self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)
        self.assertEqual(expected_lobby, lobby_after_call)
        self.mock_send_event_to_lobby.assert_not_called()

    def test_receive_question_answered_correct_answer(self):
        self.game_consumer.user_id = self.user1.id

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.current_question_count = 0
        lobby.question_start_time = datetime.now()
        lobby.save()

        expected_lobby = lobby
        expected_lobby.current_answer_count = 1

        content: QuestionAnsweredEvent = {
            "type": "question.answered",
            "answer": expected_lobby.correct_answers[0].answer,
        }

        self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(self.game_consumer.question_answered, True)
        self.mock_send_event_to_lobby.assert_called_once_with(
            "user.answered",
            {
                "user_id": self.user1.id,
                "correctly": True,
                "correct_answer": expected_lobby.correct_answers[0].answer,
                "damage": 0,
            },
        )

    def test_receive_question_answered_incorrect_answer(self):
        self.game_consumer.user_id = self.user1.id

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.current_question_count = 0
        lobby.question_start_time = datetime.now()
        lobby.save()

        expected_lobby = lobby
        expected_lobby.current_answer_count = 1
        expected_lobby.users[self.user1.id]["hp"] -= settings.QUESTION_DIFFICULTY_DAMAGE_MAP[
            expected_lobby.correct_answers[0].difficulty
        ]

        content: QuestionAnsweredEvent = {
            "type": "question.answered",
            "answer": "INCORRECT_ANSWER",
        }

        self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(self.game_consumer.question_answered, True)
        self.mock_send_event_to_lobby.assert_called_once_with(
            "user.answered",
            {
                "user_id": self.user1.id,
                "correctly": False,
                "correct_answer": expected_lobby.correct_answers[0].answer,
                "damage": settings.QUESTION_DIFFICULTY_DAMAGE_MAP[expected_lobby.correct_answers[0].difficulty],
            },
        )

    @patch("trivia.consumers.datetime")
    def test_receive_question_answered_after_max_question_duration(self, mock_datetime):
        self.game_consumer.user_id = self.user1.id

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = [
            CorrectAnswer(answer=str(i), difficulty="easy") for i in range(settings.TRIVIA_API_QUESTION_AMOUNT)
        ]
        lobby.current_question_count = 0
        lobby.question_start_time = datetime.now()
        lobby.save()

        expected_lobby = lobby
        expected_lobby.current_answer_count = 1
        correct_answer_difficulty = expected_lobby.correct_answers[0].difficulty
        expected_lobby.users[self.user1.id]["hp"] -= settings.QUESTION_DIFFICULTY_DAMAGE_MAP[correct_answer_difficulty]

        question_max_duration = settings.QUESTION_MAX_DURATION_SECONDS_MAP[correct_answer_difficulty]
        mock_datetime.now.return_value = expected_lobby.question_start_time + timedelta(
            seconds=question_max_duration + 1
        )

        content: QuestionAnsweredEvent = {
            "type": "question.answered",
            "answer": expected_lobby.correct_answers[0].answer,
        }

        self.game_consumer.receive_json(content)

        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(self.game_consumer.question_answered, True)
        self.mock_send_event_to_lobby.assert_called_once_with(
            "user.answered",
            {
                "user_id": self.user1.id,
                "correctly": False,
                "correct_answer": expected_lobby.correct_answers[0].answer,
                "damage": settings.QUESTION_DIFFICULTY_DAMAGE_MAP[correct_answer_difficulty],
            },
        )

    def test_receive_question_answered_second_time_and_user_hp_zero(self):
        self.game_consumer.user_id = self.user2.id
        self.game_consumer.determine_user_status_by_hp = MagicMock()
        self.game_consumer.handle_game_end = MagicMock()

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.current_question_count = 0
        lobby.current_answer_count = 1
        lobby.question_start_time = datetime.now()
        lobby.users[self.user1.id]["hp"] = 0
        lobby.save()

        expected_lobby = lobby

        content: QuestionAnsweredEvent = {
            "type": "question.answered",
            "answer": expected_lobby.correct_answers[0].answer,
        }

        self.game_consumer.receive_json(content)
        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(self.game_consumer.question_answered, True)
        self.game_consumer.determine_user_status_by_hp.assert_called_once_with(
            [(user_id, data["hp"]) for user_id, data in lobby.users.items()]
        )
        self.game_consumer.handle_game_end.assert_called_once_with(self.game_consumer.determine_user_status_by_hp())

    @patch("trivia.consumers.datetime")
    def test_receive_question_answered_second_time_and_game_duration_expired(self, mock_datetime):
        self.game_consumer.user_id = self.user2.id
        self.game_consumer.determine_user_status_by_hp = MagicMock()
        self.game_consumer.handle_game_end = MagicMock()

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = [
            CorrectAnswer(answer=str(i), difficulty="easy") for i in range(settings.TRIVIA_API_QUESTION_AMOUNT)
        ]
        lobby.current_question_count = 0
        lobby.current_answer_count = 1
        lobby.game_start_time = datetime.now()
        lobby.question_start_time = datetime.now()
        lobby.save()

        expected_lobby = lobby

        mock_datetime.now.side_effect = [
            expected_lobby.question_start_time,
            expected_lobby.game_start_time + timedelta(seconds=settings.GAME_MAX_DURATION_SECONDS + 1),
        ]

        content: QuestionAnsweredEvent = {
            "type": "question.answered",
            "answer": expected_lobby.correct_answers[0].answer,
        }

        self.game_consumer.receive_json(content)
        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(self.game_consumer.question_answered, True)
        self.game_consumer.determine_user_status_by_hp.assert_called_once_with(
            [(user_id, data["hp"]) for user_id, data in lobby.users.items()]
        )
        self.game_consumer.handle_game_end.assert_called_once_with(self.game_consumer.determine_user_status_by_hp())

    @patch("trivia.consumers.datetime")
    def test_receive_question_answered_second_time_game_continues(self, mock_datetime):
        self.game_consumer.user_id = self.user2.id
        self.game_consumer.determine_user_status_by_hp = MagicMock()
        self.game_consumer.handle_game_end = MagicMock()

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = [
            CorrectAnswer(answer=str(i), difficulty="easy") for i in range(settings.TRIVIA_API_QUESTION_AMOUNT)
        ]
        lobby.current_question_count = 0
        lobby.current_answer_count = 1
        lobby.game_start_time = datetime.now()
        lobby.question_start_time = datetime.now()

        lobby.save()

        expected_lobby = lobby
        expected_lobby.current_answer_count = 0
        expected_lobby.current_question_count += 1

        mock_datetime.now.return_value = expected_lobby.question_start_time

        content: QuestionAnsweredEvent = {
            "type": "question.answered",
            "answer": expected_lobby.correct_answers[0].answer,
        }

        self.game_consumer.receive_json(content)
        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(self.game_consumer.question_answered, True)
        self.game_consumer.determine_user_status_by_hp.assert_not_called()
        self.game_consumer.handle_game_end.assert_not_called()

        self.mock_send_event_to_lobby.assert_has_calls(
            (
                call(
                    "user.answered",
                    {
                        "user_id": self.user2.id,
                        "correctly": True,
                        "correct_answer": expected_lobby.correct_answers[0].answer,
                        "damage": 0,
                    },
                ),
                call("question.next"),
            ),
            any_order=False,
        )

    @patch("trivia.consumers.datetime")
    def test_receive_question_answered_second_time_questions_exhausted(self, mock_datetime):
        self.game_consumer.user_id = self.user2.id
        self.game_consumer.determine_user_status_by_hp = MagicMock()
        self.game_consumer.handle_game_end = MagicMock()
        self.game_consumer.get_and_format_questions = MagicMock()
        self.game_consumer.get_and_format_questions.return_value = (self.formatted_questions, self.correct_answers)

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.current_question_count = settings.TRIVIA_API_QUESTION_AMOUNT - 1
        lobby.current_answer_count = 1
        lobby.game_start_time = datetime.now()
        lobby.question_start_time = datetime.now()
        lobby.save()

        expected_lobby = lobby
        expected_lobby.current_answer_count = 0
        expected_lobby.current_question_count = 0

        mock_datetime.now.return_value = expected_lobby.question_start_time

        content: QuestionAnsweredEvent = {
            "type": "question.answered",
            "answer": expected_lobby.correct_answers[settings.TRIVIA_API_QUESTION_AMOUNT - 1].answer,
        }

        self.game_consumer.receive_json(content)
        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(self.game_consumer.question_answered, True)
        self.game_consumer.determine_user_status_by_hp.assert_not_called()
        self.game_consumer.handle_game_end.assert_not_called()
        self.game_consumer.get_and_format_questions.assert_called_once_with(expected_lobby.trivia_token)

        self.mock_send_event_to_lobby.assert_has_calls(
            (
                call(
                    "user.answered",
                    {
                        "user_id": self.user2.id,
                        "correctly": True,
                        "correct_answer": expected_lobby.correct_answers[
                            settings.TRIVIA_API_QUESTION_AMOUNT - 1
                        ].answer,
                        "damage": 0,
                    },
                ),
                call("question.data", {"questions": self.formatted_questions}),
                call("question.next"),
            ),
            any_order=False,
        )

    def test_receive_fifty_request_already_used(self):
        self.game_consumer.fifty_used = True

        content: FiftyRequestedEvent = {"type": "fifty.request", "answers": self.formatted_questions[0]["answers"]}

        self.game_consumer.receive_json(content)

        self.mock_send_event_to_lobby.assert_not_called()

    def test_receive_fifty_request_true_false_question(self):
        self.game_consumer.token = self.user1_token
        self.game_consumer.fifty_used = False
        self.formatted_questions[0]["answers"] = ["True", "False"]

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.correct_answers[0] = CorrectAnswer("True", "easy")
        lobby.current_question_count = 0
        lobby.save()

        content: FiftyRequestedEvent = {"type": "fifty.request", "answers": self.formatted_questions[0]["answers"]}

        self.game_consumer.receive_json(content)

        self.mock_send_event_to_lobby.assert_not_called()

    @patch("trivia.consumers.random.sample")
    def test_receive_fifty_request_multiple_choice_question(self, mock_sample):
        self.game_consumer.user_id = self.user1.id
        self.game_consumer.fifty_used = False
        self.formatted_questions[0]["answers"] = ["1", "2", "3", "4"]
        mock_sample.return_value = ["2", "4"]

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.correct_answers[0] = CorrectAnswer("1", "easy")
        lobby.current_question_count = 0
        lobby.save()

        content: FiftyRequestedEvent = {"type": "fifty.request", "answers": self.formatted_questions[0]["answers"]}

        self.game_consumer.receive_json(content)
        self.mock_send_event_to_lobby.assert_called_once_with(
            "fifty.response", {"user_id": self.game_consumer.user_id, "incorrect_answers": mock_sample.return_value}
        )

    def test_receive_fifty_request_with_incorrect_amount_of_answers(self):
        self.game_consumer.user_id = self.user1.id
        self.game_consumer.fifty_used = False
        self.formatted_questions[0]["answers"] = ["1", "2", "3", "4", "5"]

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.correct_answers[0] = CorrectAnswer("1", "easy")
        lobby.current_question_count = 0
        lobby.save()

        content: FiftyRequestedEvent = {"type": "fifty.request", "answers": self.formatted_questions[0]["answers"]}

        self.game_consumer.receive_json(content)
        self.mock_send_event_to_lobby.assert_not_called()

    def test_receive_fifty_request_with_repeated_answers(self):
        self.game_consumer.user_id = self.user1.id
        self.game_consumer.token = self.user1_token
        self.game_consumer.fifty_used = False
        self.formatted_questions[0]["answers"] = ["1", "1", "2", "3"]

        lobby = Lobby.get(self.lobby_name)
        lobby.correct_answers = self.correct_answers
        lobby.correct_answers[0] = CorrectAnswer("1", "easy")
        lobby.current_question_count = 0
        lobby.save()

        content: FiftyRequestedEvent = {"type": "fifty.request", "answers": self.formatted_questions[0]["answers"]}

        self.game_consumer.receive_json(content)
        self.mock_send_event_to_lobby.assert_not_called()

    @patch("trivia.consumers.async_to_sync")
    def test_send_event_to_lobby(self, mock_async_to_sync: MagicMock):
        mock_async_to_sync.side_effect = lambda func: func
        msg_type = "MESSAGE.TYPE"
        data = {"SOME_DATA_KEY": "SOME_DATA_VALUE"}

        self.send_event_to_lobby_patcher.stop()
        self.game_consumer.send_event_to_lobby(msg_type, data)
        self.send_event_to_lobby_patcher.start()

        mock_async_to_sync.assert_called_once_with(self.game_consumer.channel_layer.group_send)
        self.game_consumer.channel_layer.group_send.assert_called_once_with(self.lobby_name, {"type": msg_type, **data})

    @patch("trivia.consumers.async_to_sync")
    def test_send_event_to_lobby_without_data(self, mock_async_to_sync: MagicMock):
        mock_async_to_sync.side_effect = lambda func: func
        msg_type = "MESSAGE.TYPE"

        self.send_event_to_lobby_patcher.stop()
        self.game_consumer.send_event_to_lobby(msg_type)
        self.send_event_to_lobby_patcher.start()

        mock_async_to_sync.assert_called_once_with(self.game_consumer.channel_layer.group_send)
        self.game_consumer.channel_layer.group_send.assert_called_once_with(self.lobby_name, {"type": msg_type})

    def test_handle_game_end_normal(self):
        lobby = Lobby.get(self.lobby_name)
        lobby.ranked = False
        lobby.save()

        expected_lobby = lobby
        expected_lobby.state = LobbyState.FINISHED

        users = {
            self.user1.id: GameStatus.WIN,
            self.user2.id: GameStatus.LOSS,
        }

        self.game_consumer.handle_game_end(users)

        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        games = Game.objects.all()
        user_games = UserGame.objects.all()
        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(len(games), 1)
        self.assertEqual(len(user_games), 2)
        self.assertEqual(list(self.user1.games.all()), list(self.user2.games.all()))
        self.assertEqual(list(games[0].usergame_set.all()), list(user_games))
        self.assertEqual(games[0].type, GameType.NORMAL)
        self.mock_send_event_to_lobby.assert_called_once_with(
            "game.end",
            {
                "users": {
                    str(self.user1.id): {"status": GameStatus.WIN, "rank_gain": ANY},
                    str(self.user2.id): {"status": GameStatus.LOSS, "rank_gain": ANY},
                }
            },
        )

    def test_handle_game_end_ranked(self):
        expected_lobby = Lobby.get(self.lobby_name)
        expected_lobby.state = LobbyState.FINISHED

        user1_before_rank = self.user1.rank
        user2_before_rank = self.user2.rank

        users = {
            self.user1.id: GameStatus.WIN,
            self.user2.id: GameStatus.LOSS,
        }

        self.game_consumer.handle_game_end(users)

        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        games = Game.objects.all()
        user_games = UserGame.objects.all()
        lobby_after_call = Lobby.get(self.lobby_name)

        self.assertEqual(expected_lobby, lobby_after_call)
        self.assertEqual(len(games), 1)
        self.assertEqual(len(user_games), 2)
        self.assertEqual(list(self.user1.games.all()), list(self.user2.games.all()))
        self.assertEqual(list(games[0].usergame_set.all()), list(user_games))
        self.assertEqual(self.user1.rank, user1_before_rank + settings.GAME_RANK_GAIN)
        self.assertEqual(self.user2.rank, user2_before_rank - settings.GAME_RANK_GAIN)
        self.assertEqual(games[0].type, GameType.RANKED)
        self.mock_send_event_to_lobby.assert_called_once_with(
            "game.end",
            {
                "users": {
                    str(self.user1.id): {"status": GameStatus.WIN, "rank_gain": 20},
                    str(self.user2.id): {"status": GameStatus.LOSS, "rank_gain": -20},
                }
            },
        )

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_game_prepare(self, mock_send_json: MagicMock):
        event = {"type": "game.prepare"}

        self.game_consumer.game_prepare(event)

        mock_send_json.assert_called_once_with(event)

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_game_start(self, mock_send_json: MagicMock):
        event = {
            "type": "game.start",
            "duration": settings.GAME_MAX_DURATION_SECONDS,
            "users": {str(self.user1.id): self.user2.username, str(self.user2.id): self.user1.username},
        }
        self.game_consumer.user_id = self.user1.id

        self.game_consumer.game_start(event)

        mock_send_json.assert_called_once_with(
            {"type": event["type"], "duration": event["duration"], "opponent": event["users"][str(self.user1.id)]}
        )

    @patch("trivia.consumers.GameConsumer.close")
    @patch("trivia.consumers.GameConsumer.send_json")
    def test_game_end(self, mock_send_json: MagicMock, mock_close: MagicMock):
        event: GameEndEvent = {
            "type": "game.end",
            "users": {
                str(self.user1.id): {"status": GameStatus.WIN, "rank_gain": ANY},
                str(self.user2.id): {"status": GameStatus.LOSS, "rank_gain": ANY},
            },
        }
        self.game_consumer.user_id = self.user1.id

        self.game_consumer.game_end(event)

        mock_send_json.assert_called_once_with(
            {
                "type": event["type"],
                "status": event["users"][str(self.user1.id)]["status"].name.lower(),
                "rank_gain": event["users"][str(self.user1.id)]["rank_gain"],
            }
        )
        mock_close.assert_called_once()

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_question_data(self, mock_send_json: MagicMock):
        event = {
            "type": "question.data",
            "questions": ANY,
        }

        self.game_consumer.question_data(event)

        mock_send_json.assert_called_once_with(event)

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_question_next(self, mock_send_json: MagicMock):
        event = {"type": "question.next"}

        self.game_consumer.question_next(event)

        self.assertFalse(self.game_consumer.question_answered)
        mock_send_json.assert_called_once_with(event)

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_user_answered_self(self, mock_send_json: MagicMock):
        event = {
            "type": "user.answered",
            "user_id": self.user1.id,
            "correctly": True,
            "correct_answer": "CORRECT_ANSWER",
            "damage": 20,
        }
        self.game_consumer.user_id = self.user1.id

        self.game_consumer.user_answered(event)

        mock_send_json.assert_called_once_with(
            {
                "type": "question.result",
                "correctly": event["correctly"],
                "correct_answer": event["correct_answer"],
                "damage": 20,
            }
        )

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_user_answered_opponent(self, mock_send_json: MagicMock):
        event = {
            "type": "user.answered",
            "user_id": self.user1.id,
            "correctly": True,
            "correct_answer": "CORRECT_ANSWER",
            "damage": 20,
        }
        self.game_consumer.user_id = self.user2.id

        self.game_consumer.user_answered(event)

        mock_send_json.assert_called_once_with(
            {"type": "opponent.answered", "correctly": event["correctly"], "damage": 20}
        )

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_fifty_response_self(self, mock_send_json: MagicMock):
        event = {"type": "fifty.response", "incorrect_answers": ["1", "2"], "user_id": self.user1.id}
        self.game_consumer.user_id = self.user1.id

        self.game_consumer.fifty_response(event)

        mock_send_json.assert_called_once_with(event)

    @patch("trivia.consumers.GameConsumer.send_json")
    def test_fifty_response_opponent(self, mock_send_json: MagicMock):
        event = {"type": "fifty.response", "incorrect_answers": ["1", "2"], "user_id": self.user1.id}
        self.game_consumer.user_id = self.user2.id

        self.game_consumer.fifty_response(event)

        mock_send_json.assert_not_called()

    def test_determine_user_status_by_hp_equal(self):
        data = [
            (self.user1.id, 100),
            (self.user2.id, 100),
        ]

        status_dict = self.game_consumer.determine_user_status_by_hp(data)

        self.assertEqual(
            status_dict,
            {
                self.user1.id: GameStatus.DRAW,
                self.user2.id: GameStatus.DRAW,
            },
        )

    def test_determine_user_status_by_hp_user1_more(self):
        data = [
            (self.user1.id, 100),
            (self.user2.id, 50),
        ]

        status_dict = self.game_consumer.determine_user_status_by_hp(data)

        self.assertEqual(
            status_dict,
            {
                self.user1.id: GameStatus.WIN,
                self.user2.id: GameStatus.LOSS,
            },
        )

    def test_determine_user_status_by_hp_user1_less(self):
        data = [
            (self.user1.id, 50),
            (self.user2.id, 100),
        ]

        status_dict = self.game_consumer.determine_user_status_by_hp(data)

        self.assertEqual(
            status_dict,
            {
                self.user1.id: GameStatus.LOSS,
                self.user2.id: GameStatus.WIN,
            },
        )

    @patch("trivia.consumers.random.sample")
    def test_format_trivia_question_decodes_and_formats_correctly(self, mock_sample):
        mock_sample.side_effect = lambda answers, k: list(answers)

        question = "<FAKE QUESTION>"
        correct_answer = "<&FAKE_CORRECT_ANSWER&>"
        incorrect_answers = [
            "<INCORRECT_ANSWER_1>",
            "<INCORRECT&ANSWER&2>",
            "<INCORRECT_ANSWER_3&",
            "&INCORRECT_ANSWER_4>",
        ]
        question_data: TriviaAPIQuestion = {
            "category": "FAKE_CATEGORY",
            "type": "multiple",
            "difficulty": "hard",
            "question": html.escape(question),
            "correct_answer": html.escape(correct_answer),
            "incorrect_answers": [html.escape(answer) for answer in incorrect_answers],
        }

        game_consumer = GameConsumer()
        formatted_question, correct_answer_result = game_consumer.format_trivia_question(question_data)

        self.assertEqual(
            formatted_question,
            {
                "category": question_data["category"],
                "question": question,
                "duration": settings.QUESTION_MAX_DURATION_SECONDS_MAP["hard"],
                "answers": [*incorrect_answers, correct_answer],
                "difficulty": question_data["difficulty"],
                "type": question_data["type"],
            },
        )
        self.assertEqual(correct_answer, correct_answer_result)

    def test_format_trivia_question_boolean_type(self):
        question = "<FAKE QUESTION>"
        question_data: TriviaAPIQuestion = {
            "category": "FAKE_CATEGORY",
            "type": "boolean",
            "difficulty": "hard",
            "question": html.escape(question),
            "correct_answer": "False",
            "incorrect_answers": ["True"],
        }

        game_consumer = GameConsumer()
        formatted_question, correct_answer = game_consumer.format_trivia_question(question_data)

        self.assertEqual(
            formatted_question,
            {
                "category": question_data["category"],
                "question": question,
                "duration": settings.QUESTION_MAX_DURATION_SECONDS_MAP["hard"],
                "answers": ["True", "False"],
                "difficulty": question_data["difficulty"],
                "type": question_data["type"],
            },
        )
        self.assertEqual(correct_answer, question_data["correct_answer"])
