import asyncio
import json
from collections import deque
from contextlib import suppress
from typing import Optional

import websockets
from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Static

from .exceptions import ResponseError
from .messages import FiftyFiftyTriggered, QuestionAnswered, TrainingQuestionAnswered
from .types import TrainingQuestionData
from .utils import decode_training_questions
from .widgets import (
    BackButton,
    ConfirmLeaveModal,
    GameHeader,
    GameHistoryTable,
    GameStatus,
    Question,
    TrainingQuestion,
)


class LoginOrRegisterScreen(Screen):
    """
    Authentication screen from where the user can either log in or register

    The first screen of the app. Without authentication the user can not access
    the app.
    """

    def compose(self) -> ComposeResult:
        yield Input(placeholder="username", id="username")
        yield Input(placeholder="password", id="password", password=True)
        yield Button("Login", id="btn-login")
        yield Button("Register", id="btn-register")

    async def on_button_pressed(self, event: Button.Pressed):
        username, password = self.query_credentials()

        if event.button.id == "btn-register":
            try:
                self.app.client.register(username, password)
                await self.app.push_screen(InfoScreen("Successfully registered!"))
            except ResponseError as e:
                await self.app.push_screen(ErrorScreen(e))

        elif event.button.id == "btn-login":
            try:
                self.app.client.login(username, password)
                self.app.username = username
                await self.app.push_screen(MainMenuScreen())
            except ResponseError as e:
                await self.app.push_screen(ErrorScreen(e))

    def query_credentials(self) -> tuple[str, str]:
        username = self.query_one("#username").value
        password = self.query_one("#password").value
        return username, password


class MainMenuScreen(Screen):
    """Main menu screen from which the user has access to all of app's functionality"""

    def compose(self) -> ComposeResult:
        yield Button("Play", id="btn-play")
        yield Button("Leaderboard", id="btn-leaderboard")
        yield Button("History", id="btn-history")
        yield BackButton("Back")

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-play":
            await self.app.push_screen(PlayMenuScreen())
        elif event.button.id == "btn-leaderboard":
            await self.app.push_screen(UserRankingScreen())
        elif event.button.id == "btn-history":
            await self.app.push_screen(GameHistoryScreen())


class PlayMenuScreen(Screen):
    """Play screen from which the user has access to different trivia game modes"""

    def compose(self) -> ComposeResult:
        yield Button("Ranked", id="btn-ranked")
        yield Button("Normal", id="btn-normal")
        yield Button("Training", id="btn-training")
        yield BackButton("Back")

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-ranked":
            await self.app.push_screen(JoinOrHostScreen("ranked"))
        elif event.button.id == "btn-normal":
            await self.app.push_screen(JoinOrHostScreen("normal"))
        else:
            await self.app.push_screen(TrainingScreen())


class TrainingScreen(Screen):
    """
    Screen where the training games are played out. The user is given 10 trivia questions
    that they have to answer, there is no time limit and the user is also allowed to skip over questions.
    Skipped questions will reappear after all other questions.

    After the user has answered all questions, the client saves a record
    of the played game on the server.
    """

    def __init__(self):
        self.questions: Optional[deque[TrainingQuestionData]] = None
        super().__init__()

    async def on_mount(self):
        """On mount: obtain questions and display the first question"""
        try:
            self.questions = deque(decode_training_questions(self.app.client.get_training_questions()))
            await self.mount(TrainingQuestion(self.questions[0]))
            await self.mount(Button("Skip", id="btn-action"))
        except ResponseError as e:
            await self.app.fixed_switch_screen(ErrorScreen(e))

    async def on_training_question_answered(self, _event: TrainingQuestionAnswered):
        """
        Every time a question is answered, the correct answer is highlighted and a Next button appears,
        that the user can use to move to the next question.

        If all questions have been answered, the app attempts to save the record of the training game
        on the server.
        """
        if len(self.questions) > 1:
            self.query_one("#btn-action").label = "Next"
            return

        try:
            self.app.client.post_training_result()
        except ResponseError as e:
            await self.app.fixed_switch_screen(ErrorScreen(e))
            return

        await self.query_one("#btn-action").remove()
        await self.mount(BackButton("Finish"))

    async def on_button_pressed(self, event: Button.Pressed):
        match str(event.button.label):
            case "Skip":
                self.questions.append(self.questions.popleft())
            case "Next":
                self.questions.popleft()
            case _:
                return

        await self.mount_next_question()

    async def clear_widgets(self) -> None:
        """Remove all widgets from the screen and reset widget focus to None"""

        for child in self.walk_children():
            await child.remove()

        self.set_focus(None)

    async def mount_next_question(self) -> None:
        """Remove all widgets and mount a new instance of Training Question and action button"""

        await self.clear_widgets()
        await self.mount(TrainingQuestion(self.questions[0]))
        await self.mount(Button("Skip", id="btn-action"))

    async def on_key(self, event: events.Key):
        if event.key == "escape":
            await self.clear_widgets()


class JoinOrHostScreen(Screen):
    """
    Screen from which the user can choose to either join or host a multiplayer game.
    """

    def __init__(self, game_type: str):
        self.game_type = game_type
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Button("Join", id="btn-join")
        yield Button("Host", id="btn-host")
        yield BackButton("Back")

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-host":
            await self.app.push_screen(HostScreen(self.game_type))
        elif event.button.id == "btn-join":
            await self.app.push_screen(JoinScreen(self.game_type))


class HostScreen(Screen):
    """Screen from which the user can host a multiplayer game."""

    def __init__(self, game_type: str):
        self.game_type = game_type
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Lobby Name", id="lobby-name")
        yield Button("Create")
        yield BackButton("Back")

    async def on_button_pressed(self, event: Button.Pressed):
        """
        Try to create a lobby on the server with the inputted name.
        """

        event.prevent_default()
        lobby_name = self.query_one("#lobby-name").value

        try:
            data = self.app.client.create_lobby(lobby_name, ranked=self.game_type == "ranked")
        except ResponseError as e:
            await self.app.push_screen(ErrorScreen(e))
            return

        await self.app.fixed_switch_screen(GameScreen(lobby_name, data["token"]))

    def on_screen_resume(self):
        self.query_one(Input).value = ""


class JoinScreen(Screen):
    """Screen from which the user can join a multiplayer game."""

    def __init__(self, game_type: str):
        self.game_type = game_type
        super().__init__()

    def compose(self) -> ComposeResult:
        """List all available lobbies"""
        try:
            lobbies = self.app.client.get_lobbies(ranked=self.game_type == "ranked")
        except ResponseError as e:
            self.app.switch_screen(ErrorScreen(e))
            return

        if not lobbies:
            yield Static("There are no lobbies")
            yield BackButton("Back")
            return

        for lobby in lobbies:
            yield Button(f"{lobby['name']} {lobby['player_count']}/2")

        yield BackButton("Go Back")

    async def on_button_pressed(self, event: Button.Pressed):
        """When a user presses on a lobby, try to connect to it"""
        lobby_name = str(event.button.label).split()[0]

        try:
            data = self.app.client.join_lobby(lobby_name)
        except ResponseError as e:
            await self.app.fixed_switch_screen(ErrorScreen(e))
            return

        await self.app.fixed_switch_screen(GameScreen(lobby_name, data["token"]))


class GameScreen(Screen):
    """
    Screen from which a multiplayer game is played. Used to play both
    ranked and normal game modes.
    """

    def __init__(self, lobby: str, token: str):
        self.lobby = lobby
        self.token = token
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

        self.questions: Optional[list[dict]] = None
        self.current_question: int = 0
        self.first_question_received: bool = False
        self.fifty_fifty_chance: bool = True
        self.game_in_progress: bool = False

        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static("Waiting for an opponent...", id="static-info")

    async def on_mount(self):
        """
        Try to connect to a lobby on the server and initiate
        a coroutine that listens for incoming events.
        """
        self.ws = await self.app.client.ws_join_lobby(self.lobby, self.token)
        asyncio.create_task(self.receive_ws())

    async def receive_ws(self) -> None:
        """Coroutine that listens for incoming websocket events from the server"""

        with suppress(websockets.ConnectionClosedOK):
            while True:
                event = await self.ws.recv()
                await self.handle_ws_event(json.loads(event))

    async def handle_ws_event(self, event) -> None:
        """Handle an event received from the server"""

        if event["type"] == "game.prepare":
            """Show the user that the game is starting"""
            self.game_in_progress = True

            info = self.query_one("#static-info", Static)
            info.renderable = "Opponent found! Loading in..."
            info.refresh()
            confirm_leave = ConfirmLeaveModal(id="confirm-leave")
            confirm_leave.display = "none"
            await self.mount(confirm_leave)

            await self.ws.send(json.dumps({"type": "game.ready"}))

        elif event["type"] == "game.start":
            """Mount game components"""
            opponent_name = event["opponent"]
            duration = event["duration"]

            confirm_leave = self.query_one("#confirm-leave", ConfirmLeaveModal)
            confirm_leave.display = "none"
            await self.query_one("#static-info", Static).remove()
            await self.mount(GameHeader(self.app.username, opponent_name, duration), before=confirm_leave)
            await self.mount(Container(id="container-question"))

        elif event["type"] == "question.data":
            """Store a new set of questions"""
            self.questions = event["questions"]
            self.current_question = 0

        elif event["type"] == "question.next":
            """Load in the next question"""
            if self.first_question_received:
                # Take some time before mounting the next question to allow
                # the user to view the correct answer.
                await asyncio.sleep(1)
            else:
                self.first_question_received = True

            await self.next_question()

        elif event["type"] == "question.result":
            """Show the correct answer of the question"""
            question_container = self.query_one("#container-question", Container)
            question_container.query_one(Question).highlight_answers(event["correct_answer"], event["correctly"])
            self.query_one(GameHeader).decrease_player_hp(int(event["damage"]))

        elif event["type"] == "fifty.response":
            """Try to use the 50/50 ability"""
            await self.query_one(Question).post_message(
                FiftyFiftyTriggered(self, incorrect_answers=event["incorrect_answers"])
            )

        elif event["type"] == "game.end":
            """End the game and disconnect from the websocket connection"""
            self.game_in_progress = False
            await asyncio.sleep(1)
            await self.game_end(event["status"])

        elif event["type"] == "opponent.answered":
            """Update the opponents hp"""
            self.query_one(GameHeader).decrease_opponent_hp(int(event["damage"]))

    async def next_question(self) -> None:
        """Remove the previous question and mount the next one"""
        question_container = self.query_one("#container-question", Container)
        for child in question_container.walk_children():
            await child.remove()
        self.set_focus(None)

        await question_container.mount(Question(self.questions[self.current_question]))

        if self.fifty_fifty_chance:
            await question_container.mount(Button("50/50", id="btn-5050"))

        self.current_question += 1

    async def on_question_answered(self, event: QuestionAnswered):
        """
        Whenever the user answers a question, a question.answered event is sent to the server
        """

        if self.fifty_fifty_chance:
            question_container = self.query_one("#container-question", Container)
            question_container.query_one("#btn-5050", Button).disabled = True

        await self.ws.send(json.dumps({"type": "question.answered", "answer": event.answer}))

    async def game_end(self, status: str) -> None:
        await self.ws.close()
        await self.clear_widgets()

        await self.mount(GameStatus(status))
        await self.mount(BackButton("Leave"))

    async def on_button_pressed(self, event: Button.Pressed):
        match event.button.id:
            case "btn-5050":
                self.fifty_fifty_chance = False
                await event.button.remove()
                await self.ws.send(
                    json.dumps(
                        {"type": "fifty.request", "answers": self.questions[self.current_question - 1]["answers"]}
                    )
                )
            case "confirm-accept":
                if self.ws:
                    await self.ws.close()
                await self.clear_widgets()
                await self.app.fixed_pop_screen()
            case "confirm-reject":
                self.query_one("#confirm-leave").display = "none"

                try:
                    self.query_one("#container-question").display = "block"
                except NoMatches:
                    pass

                self.set_focus(None)
            case _:
                raise Exception("Unexpected button event received")

    async def on_key(self, event: events.Key):
        """
        If a user tries to leave the game, show them a confirmation modal
        to make sure they want to leave.
        """
        if event.key == "escape":
            if not self.game_in_progress:
                if self.ws:
                    await self.ws.close()
                return

            event.prevent_default()

            confirm_leave = self.query_one("#confirm-leave")
            confirm_leave.display = "none" if confirm_leave.display else "block"

            try:
                question_container = self.query_one("#container-question")
                question_container.display = "none" if question_container.display else "block"
            except NoMatches:
                pass

            self.set_focus(None)

    async def clear_widgets(self) -> None:
        for child in self.walk_children():
            await child.remove()

        self.set_focus(None)


class UserRankingScreen(Screen):
    """The leaderboards screen, shows a table of all players and their ranks"""

    def compose(self) -> ComposeResult:
        yield BackButton("Back")
        yield DataTable()

    async def on_mount(self):
        try:
            rankings = ((ranking["username"], str(ranking["rank"])) for ranking in self.app.client.get_rankings())
        except ResponseError as e:
            await self.app.fixed_switch_screen(ErrorScreen(e))
            return

        table = self.query_one(DataTable)
        table.add_columns("user", "rank")

        table.add_rows(rankings)

        table.focus()


class GameHistoryScreen(Screen):
    """The history screen, shows a table of all games played by the user."""

    def compose(self) -> ComposeResult:
        try:
            games = self.app.client.get_user_games()
        except ResponseError as e:
            self.app.fixed_switch_screen(ErrorScreen(e))
            return

        if games:
            yield BackButton("Back")
            yield GameHistoryTable(games)
            return

        yield Static("You have not played any games yet!")
        yield BackButton("Back")

    async def on_mount(self):
        try:
            self.query_one(GameHistoryTable).focus()
        except NoMatches:
            pass


class InfoScreen(Screen):
    """Simple information screen to display some text and a back button"""

    def __init__(self, msg: str, *args, **kwargs):
        self.msg = msg
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        yield Static(self.msg)
        yield BackButton("Okay")


class ErrorScreen(Screen):
    """
    An error screen, used to display any errors produced when
    trying to communicate with the server.
    """

    def __init__(self, error: ResponseError, *args, **kwargs):
        self.error = error
        super().__init__(*args, **kwargs)

    def compose(self) -> ComposeResult:
        """
        The screen expects the supplied ResponseError to have a dict argument, that either contains
        a key "detail", or multiple keys that contain an array of error messages.
        """
        if self.error.error.get("detail"):
            yield Static(self.error.error.get("detail"))
        else:
            for field, errors in self.error.error.items():
                yield from (Static(f"{field}: {error}") for error in errors)

        yield BackButton("Okay")
