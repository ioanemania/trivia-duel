import html
import random
from datetime import datetime, timedelta
from itertools import chain
from typing import Optional

from asgiref.sync import async_to_sync
from channels.exceptions import AcceptConnection, DenyConnection
from channels.generic.websocket import JsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from jwt.exceptions import InvalidTokenError
from redis_om.model.model import NotFoundError

from .models import Game, Lobby, LobbyState
from .types import (
    HP,
    ClientEvent,
    CorrectAnswer,
    FiftyRequestedEvent,
    GameEndEvent,
    GameStatus,
    GameType,
    QuestionAnsweredEvent,
    TriviaAPIQuestion,
    UserId,
    UserStatus,
)
from .utils import TriviaAPIClient, decode_lobby_token

User = get_user_model()


class GameConsumer(JsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        self.lobby_name: Optional[str] = None
        self.user_id: Optional[int] = None
        self.fifty_used: bool = False
        self.ready_sent: bool = False
        self.question_answered: bool = False

        super().__init__(*args, **kwargs)

    def get_token_from_query_string(self) -> str:
        return self.scope["query_string"].decode()

    def connect(self):
        self.lobby_name = self.scope["url_route"]["kwargs"]["lobby_name"]

        try:
            lobby = Lobby.get(self.lobby_name)
        except NotFoundError:
            raise DenyConnection()

        if len(lobby.users) > 1:
            raise DenyConnection()

        token = self.get_token_from_query_string()
        try:
            token_data = decode_lobby_token(token)
        except InvalidTokenError:
            raise DenyConnection()

        if lobby.users.get(token_data["id"]):
            raise DenyConnection()

        lobby.users[token_data["id"]] = {"name": token_data["username"], "hp": 100}

        self.user_id = token_data["id"]

        async_to_sync(self.channel_layer.group_add)(self.lobby_name, self.channel_name)

        if len(lobby.users) == 1:
            Lobby.db().persist(lobby.key())
        elif len(lobby.users) == 2:
            self.send_event_to_lobby("game.prepare")

        lobby.save()

        raise AcceptConnection()

    def disconnect(self, code):
        if not self.user_id:
            return

        lobby = Lobby.get(self.lobby_name)

        # If both users have disconnected, the lobby is deleted.
        if len(lobby.users) == 1:
            Lobby.delete(lobby.name)
            async_to_sync(self.channel_layer.group_discard)(self.lobby_name, self.channel_name)
            return

        async_to_sync(self.channel_layer.group_discard)(self.lobby_name, self.channel_name)

        if lobby.state == LobbyState.IN_PROGRESS:
            # If one of the users disconnected, but the game was still in progress declare the in game user a winner
            opponent_user_id = next(user_id for user_id in lobby.users.keys() if user_id != self.user_id)
            self.handle_game_end(
                {
                    self.user_id: GameStatus.LOSS,
                    opponent_user_id: GameStatus.WIN,
                }
            )

        del lobby.users[self.user_id]
        lobby.save()

    def receive_json(self, event: ClientEvent, **kwargs):
        """
        Try to call a handler associated with the received event type.
        """

        if not (event_type := event.get("type")):
            return

        match event_type:
            case "game.ready":
                self.receive_game_ready(event)
            case "question.answered":
                event: QuestionAnsweredEvent
                self.receive_question_answered(event)
            case "fifty.request":
                event: FiftyRequestedEvent
                self.receive_fifty_request(event)
            case _:
                return

    def receive_game_ready(self, _content: dict):
        lobby = Lobby.get(self.lobby_name)
        if len(lobby.users) != 2 or lobby.ready_count >= 2 or self.ready_sent:
            return

        lobby.ready_count += 1
        self.ready_sent = True

        if lobby.ready_count == 1:
            lobby.save()
            return

        lobby.trivia_token = TriviaAPIClient.get_token()
        lobby.state = LobbyState.IN_PROGRESS
        lobby.game_start_time = datetime.now()
        self.send_event_to_lobby(
            "game.start",
            {
                "users": {
                    str(user_id): lobby.users[opponent_id]["name"]
                    for user_id, opponent_id in zip(lobby.users.keys(), reversed(lobby.users.keys()))
                },
                "duration": settings.GAME_MAX_DURATION_SECONDS,
            },
        )
        formatted_questions, correct_answers = self.get_and_format_questions(lobby.trivia_token)
        lobby.correct_answers = correct_answers
        self.send_event_to_lobby("question.data", {"questions": formatted_questions})
        lobby.question_start_time = datetime.now()
        self.send_event_to_lobby("question.next")

        lobby.save()

    def receive_question_answered(self, event: QuestionAnsweredEvent):
        lobby = Lobby.get(self.lobby_name)

        if self.question_answered:
            return

        self.question_answered = True

        correct_answer = lobby.correct_answers[lobby.current_question_count]

        question_max_duration = timedelta(seconds=settings.QUESTION_MAX_DURATION_SECONDS_MAP[correct_answer.difficulty])
        if (
            event["answer"] != correct_answer.answer
            or datetime.now() > lobby.question_start_time + question_max_duration
        ):
            correctly = False
            damage = settings.QUESTION_DIFFICULTY_DAMAGE_MAP[correct_answer.difficulty]
            lobby.users[self.user_id]["hp"] -= damage
        else:
            damage = 0
            correctly = True

        self.send_event_to_lobby(
            "user.answered",
            {
                "user_id": self.user_id,
                "correctly": correctly,
                "correct_answer": correct_answer.answer,
                "damage": damage,
            },
        )

        # question has been answered for the first time
        if lobby.current_answer_count == 0:
            lobby.current_answer_count += 1
            lobby.save()
            return

        # otherwise, both users have answered the question

        if any(
            user for user in lobby.users.values() if user["hp"] <= 0
        ) or datetime.now() > lobby.game_start_time + timedelta(seconds=settings.GAME_MAX_DURATION_SECONDS):
            self.handle_game_end(
                self.determine_user_status_by_hp(list((user_id, data["hp"]) for user_id, data in lobby.users.items()))
            )
            return

        # current set of questions has been exhausted, obtain new ones
        if lobby.current_question_count == settings.TRIVIA_API_QUESTION_AMOUNT - 1:
            lobby.current_question_count = 0

            formatted_questions, correct_answer = self.get_and_format_questions(lobby.trivia_token)
            lobby.correct_answers = correct_answer
            self.send_event_to_lobby("question.data", {"questions": formatted_questions})
        else:
            lobby.current_question_count += 1

        lobby.current_answer_count = 0
        lobby.question_start_time = datetime.now()
        lobby.save()

        self.send_event_to_lobby("question.next")

    def receive_fifty_request(self, event: FiftyRequestedEvent):
        if self.fifty_used:
            return

        self.fifty_used = True

        lobby = Lobby.get(self.lobby_name)
        correct_answer = lobby.correct_answers[lobby.current_question_count].answer
        if correct_answer in ("True", "False") or len(event["answers"]) != 4:
            return

        incorrect_answers = tuple(answer for answer in event["answers"] if answer != correct_answer)
        if len(incorrect_answers) != 3:
            return

        random_incorrect_answers = random.sample(incorrect_answers, k=2)
        self.send_event_to_lobby(
            "fifty.response", {"user_id": self.user_id, "incorrect_answers": random_incorrect_answers}
        )

    def send_event_to_lobby(self, msg_type: str, data: dict = None) -> None:
        """Wrapper function to broadcast messages to the lobby's channel group"""

        if data is None:
            data = {}

        async_to_sync(self.channel_layer.group_send)(self.lobby_name, {"type": msg_type, **data})

    def handle_game_end(self, users: dict[UserId, GameStatus]) -> None:
        lobby = Lobby.get(self.lobby_name)
        lobby.state = LobbyState.FINISHED
        lobby.save()

        user_status_dict: dict[str, UserStatus] = {}
        user1, user2 = User.objects.filter(pk__in=(users.keys()))
        user1_status, user2_status = users[user1.pk], users[user2.pk]

        for user, status in (user1, user1_status), (user2, user2_status):
            rank_gain = self.determine_rank_gain_by_game_status(status)
            if lobby.ranked:
                user.rank = max(user.rank + rank_gain, 0)
                user.save()

            user_status_dict[str(user.pk)] = {"status": status, "rank_gain": rank_gain}

        Game.objects.save_multiplayer_game(
            game_type=GameType.RANKED if lobby.ranked else GameType.NORMAL,
            user1=user1,
            user2=user2,
            user1_status=user1_status,
            user2_status=user2_status,
        )

        self.send_event_to_lobby("game.end", {"users": user_status_dict})

    def game_prepare(self, event: dict):
        self.send_json(event)

    def game_start(self, event: dict):
        opponent = event["users"][str(self.user_id)]

        self.send_json({"type": event["type"], "duration": event["duration"], "opponent": opponent})

    def game_end(self, event: GameEndEvent):
        user_status = event["users"][str(self.user_id)]
        status = GameStatus(user_status["status"]).name.lower()

        self.send_json({"type": event["type"], "status": status, "rank_gain": user_status["rank_gain"]})

        self.close()

    def question_data(self, event: dict):
        self.send_json(event)

    def question_next(self, event: dict):
        self.question_answered = False
        self.send_json(event)

    def user_answered(self, event: dict):
        message = {
            "correctly": event["correctly"],
            "correct_answer": event["correct_answer"],
            "damage": event["damage"],
        }

        if event["user_id"] == self.user_id:
            message["type"] = "question.result"
        else:
            message["type"] = "opponent.answered"
            del message["correct_answer"]

        self.send_json(message)

    def fifty_response(self, event: dict):
        if event["user_id"] == self.user_id:
            self.send_json(event)

    def determine_user_status_by_hp(self, users: list[tuple[UserId, HP]]) -> dict[UserId, GameStatus]:  # noqa
        """Determine the win/loss/draw status of both users based on their hp"""

        user1_id, user1_hp = users[0]
        user2_id, user2_hp = users[1]

        if user1_hp == user2_hp:
            user1_status = user2_status = GameStatus.DRAW
        elif user1_hp > user2_hp:
            user1_status, user2_status = GameStatus.WIN, GameStatus.LOSS
        else:
            user1_status, user2_status = GameStatus.LOSS, GameStatus.WIN

        return {
            user1_id: user1_status,
            user2_id: user2_status,
        }

    def determine_rank_gain_by_game_status(self, status: GameStatus) -> int:  # noqa
        return {GameStatus.WIN: settings.GAME_RANK_GAIN, GameStatus.LOSS: -settings.GAME_RANK_GAIN, GameStatus.DRAW: 0}[
            status
        ]

    def get_and_format_questions(self, trivia_token: str) -> tuple[list[dict], list[CorrectAnswer]]:
        correct_answers = []
        formatted_questions = []

        for question in TriviaAPIClient.get_questions(trivia_token):
            formatted_question, correct_answer = self.format_trivia_question(question)
            formatted_questions.append(formatted_question)
            correct_answer_data = CorrectAnswer(
                answer=correct_answer,
                difficulty=formatted_question["difficulty"],
            )
            correct_answers.append(correct_answer_data)

        return formatted_questions, correct_answers

    def format_trivia_question(self, question: TriviaAPIQuestion) -> tuple[dict, str]:  # noqa
        if question["type"] == "boolean":
            answers = ["True", "False"]
        else:
            encoded_answers = chain(question["incorrect_answers"], (question["correct_answer"],))
            decoded_answers = tuple(html.unescape(answer) for answer in encoded_answers)
            answers = random.sample(decoded_answers, k=len(decoded_answers))

        return {
            "category": question["category"],
            "question": html.unescape(question["question"]),
            "answers": answers,
            "difficulty": question["difficulty"],
            "duration": settings.QUESTION_MAX_DURATION_SECONDS_MAP[question["difficulty"]],
            "type": question["type"],
        }, html.unescape(question["correct_answer"])
