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
    FormattedQuestion,
    GameEndEvent,
    GamePrepareEvent,
    GameStartEvent,
    GameStatus,
    GameType,
    QuestionAnsweredEvent,
    QuestionDataEvent,
    QuestionNextEvent,
    TriviaAPIQuestion,
    UserAnsweredEvent,
    UserId,
    UserStatus,
)
from .utils import TriviaAPIClient, decode_lobby_token

User = get_user_model()


class GameConsumer(JsonWebsocketConsumer):
    """
    Consumer that is used to play a multiplayer trivia game.

    The game is played out by the users and the consumer communicating
    different events with each other.

    Expected User events are:
        - game.ready => sent when a user is ready to start the game
        - question.answered => sent when a user has answered a question
        - fifty.request => sent when a user wants to use their 50/50 chance

    Defined Consumer events are:
        - game.prepare => tell users that the game is ready to be started
        - game.start => tell users that the game has started
        - game.end => tell users that the game has ended
        - question.data => give users a new set of questions
        - question.next => tell users that they should start answering the next question
        - question.result => tell a user how they answered a question
        - opponent.answered => tell a user how their opponent answered a question
    """

    def __init__(self, *args, **kwargs):
        self.lobby_name: Optional[str] = None
        self.user_id: Optional[int] = None
        self.fifty_used: bool = False
        self.ready_sent: bool = False
        self.question_answered: bool = False

        super().__init__(*args, **kwargs)

    def get_token_from_query_string(self) -> str:
        """
        Extracts the lobby authentication token from the query string.

        Token is expected to be passed in as the full query string,
        so for example /my_lobby?the_authentication_token

        Returns:
            base64 encoded JWT
        """
        return self.scope["query_string"].decode()

    def connect(self):
        """
        Validate that the user is authenticated and try to connect them to a lobby.

        Users are expected to provide a lobby authentication token which is generated
        by the Server API on join and create actions. Users are expected to provide the token
        as the query string of the websocket request.
        """
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

        if token_data["lobby_name"] != self.lobby_name:
            raise DenyConnection()

        if lobby.users.get(token_data["id"]):
            raise DenyConnection()

        lobby.users[token_data["id"]] = {"name": token_data["username"], "hp": 100}

        self.user_id = token_data["id"]

        async_to_sync(self.channel_layer.group_add)(self.lobby_name, self.channel_name)

        if len(lobby.users) == 1:
            # Lobbies are created with an expiration time, after the first user
            # connects, the expiration time should be removed.
            Lobby.db().persist(lobby.key())
        elif len(lobby.users) == 2:
            # Whenever the second user successfully connects to a lobby, the game is ready to be started.
            # An event is sent to the users to notify them that the game is ready to be started.
            # Server awaits user responses to start the game.
            self.send_event_to_lobby("game.prepare")

        lobby.save()

        raise AcceptConnection()

    def disconnect(self, code):
        """
        Removes a connected user from the lobby.

        Lobby is also deleted if it is left without any players.

        If a user disconnects when a game is in progress, the game ends with
        the user being counted as the loser.
        """
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

    def receive_game_ready(self, _event: dict):
        """
        Client event that notifies the server when a user is ready to start the game.

        When both users become ready, the game is started. The state of the lobby is initialized
        and the first set of trivia questions are obtained from the Trivia API.

        Events are sent to the users to:
            - notify them about the start of the game
            - send them the initial questions
            - notify them to start answering the first question
        """
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
        """
        Client event that notifies the server that a user has answered a question.

        Whenever a user answers a question, an event is sent back in response to both users,
        to notify them how the question was answered.

        When both users answer the question, the current question count is checked to
        determine if users have answered all the currently available questions. If so,
        a new set of questions is obtained from the Trivia API and sent to the users.

        When both users answer the question, two checks happens to try and determine
        if the game has ended. These checks are:
            - Check to see if any of the users have 0 health points
            - Check to see if maximum game duration has expired

        If any of those checks are true, the game is ended and a corresponding event is sent to the user
        to notify them that the game has ended.

        If the game has not ended the users are notified to continue to the next question.
        """
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
        """
        Client event that notifies the server that a user wants to use their 50/50 chance.

        50/50 chance allows the user to eliminate two answers for the question if that question
        is not a true/false question. Two random incorrect answers are chosen and sent back to the
        user. The server does not store incorrect answers on its side, incorrect answers are expected
        to be received from the user.

        Users have access to this ability only once, so any 50/50 event that is sent after the first
        one is ignored.
        """
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
        self.send_json({"type": "fifty.response", "incorrect_answers": random_incorrect_answers})

    def send_event_to_lobby(self, msg_type: str, data: dict = None) -> None:
        """Wrapper function to broadcast messages to the lobby's channel group"""

        if data is None:
            data = {}

        async_to_sync(self.channel_layer.group_send)(self.lobby_name, {"type": msg_type, **data})

    def handle_game_end(self, users: dict[UserId, GameStatus]) -> None:
        """
        Stores a record of the game and associated information in the database,
        updates user ranks if the game was ranked and send an event to the users to notify them
        about the results of the game.
        """
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

    def game_prepare(self, event: GamePrepareEvent):
        self.send_json(event)

    def game_start(self, event: GameStartEvent):
        opponent = event["users"][str(self.user_id)]

        self.send_json({"type": event["type"], "duration": event["duration"], "opponent": opponent})

    def game_end(self, event: GameEndEvent):
        user_status = event["users"][str(self.user_id)]
        status = GameStatus(user_status["status"]).name.lower()

        self.send_json({"type": event["type"], "status": status, "rank_gain": user_status["rank_gain"]})

        self.close()

    def question_data(self, event: QuestionDataEvent):
        self.send_json(event)

    def question_next(self, event: QuestionNextEvent):
        self.question_answered = False
        self.send_json(event)

    def user_answered(self, event: UserAnsweredEvent):
        """
        user.answered event is split and sent as two different events:
            - question.result: is sent to the user that answered the question
            - opponent.answered: is sent to that users opponent (the other user)
        """
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

    def determine_user_status_by_hp(self, users: list[tuple[UserId, HP]]) -> dict[UserId, GameStatus]:  # noqa
        """
        Determine the win/loss/draw status of both users based on their hp.

        Args:
            users: list of tuples of the user's id and hp

        Returns:
            A dictionary with keys and values corresponding to the users' ids and determined game statuses

        """
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
        match status:
            case GameStatus.WIN:
                return settings.GAME_RANK_GAIN
            case GameStatus.LOSS:
                return -settings.GAME_RANK_GAIN
            case GameStatus.DRAW:
                return 0

    def get_and_format_questions(self, trivia_token: str) -> tuple[list[FormattedQuestion], list[CorrectAnswer]]:
        """
        Obtains a set of questions from the Trivia API and returns them in an appropriate
        format alongside a list containing the correct answer for each question.

        Args:
            trivia_token: Trivia API token that is used for the current session of requests.
                          the API token is needed to guarantee unique questions between
                          subsequent calls to the API.

        Returns:
            A tuple containing the list of formatted questions and the list of correct answers.
            A correct answer is a tuple containing the correct answer and its difficulty.
        """
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

    def format_trivia_question(self, question: TriviaAPIQuestion) -> tuple[FormattedQuestion, str]:  # noqa
        """
        Formats a question obtained from the Trivia API and returns it alongside the question's
        correct answer.

        Formatting involves: mixing and randomizing correct and incorrect answers, un-escaping
        html escaped characters and calculating the questions maximum allowed duration.

        Args:
            question: the question to be formatted

        Returns:
            A tuple of the formatted question and the correct answer
        """
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
