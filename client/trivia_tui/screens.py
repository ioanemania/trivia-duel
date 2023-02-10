from collections import deque

import asyncio
import json
import websockets
from contextlib import suppress
from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, Input, Static, DataTable
from typing import Optional

from .messages import TrainingQuestionAnswered, FiftyFiftyTriggered, QuestionAnswered
from .types import TrainingQuestionData
from .utils import decode_training_questions
from .widgets import Question, GameStatus, GameHistoryTable, GameHeader, TrainingQuestion


class LoginOrRegisterScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Input(placeholder="username", id="username")
        yield Input(placeholder="password", id="password", password=True)
        yield Button("Login", id="btn-login")
        yield Button("Register", id="btn-register")

    async def on_button_pressed(self, event: Button.Pressed):
        username, password = self.query_credentials()

        # TODO: error handling
        if event.button.id == "btn-register":
            self.app.client.register(username, password)
        elif event.button.id == "btn-login":
            self.app.client.login(username, password)
            self.app.username = username
            await self.app.push_screen(MainMenuScreen())

    def query_credentials(self) -> tuple[str, str]:
        username = self.query_one("#username").value
        password = self.query_one("#password").value
        return username, password


class MainMenuScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Button("Play", id="btn-play")
        yield Button("Leaderboard", id="btn-leaderboard")
        yield Button("History", id="btn-history")

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-play":
            await self.app.push_screen(PlayMenuScreen())
        elif event.button.id == "btn-leaderboard":
            await self.app.push_screen(UserRankingScreen())
        elif event.button.id == "btn-history":
            await self.app.push_screen(GameHistoryScreen())


class PlayMenuScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Button("Ranked", id="btn-ranked")
        yield Button("Normal", id="btn-normal")
        yield Button("Training", id="btn-training")

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-ranked":
            await self.app.push_screen(JoinOrHostScreen("ranked"))
        elif event.button.id == "btn-normal":
            await self.app.push_screen(JoinOrHostScreen("normal"))
        else:
            await self.app.push_screen(TrainingScreen())


class TrainingScreen(Screen):
    def __init__(self):
        self.questions: Optional[deque[TrainingQuestionData]] = None
        super().__init__()

    def on_mount(self):
        self.questions = deque(decode_training_questions(self.app.client.get_training_questions()))

        self.mount(TrainingQuestion(self.questions[0]))
        self.mount(Button("Skip", id="btn-action"))

    async def on_training_question_answered(self, _event: TrainingQuestionAnswered):
        if len(self.questions) > 1:
            self.query_one("#btn-action").label = "Next"
            return

        self.app.client.post_training_result()
        await self.query_one("#btn-action").remove()

    async def on_button_pressed(self, event: Button.Pressed):
        match str(event.button.label):
            case "Skip":
                self.questions.append(self.questions.popleft())
            case "Next":
                self.questions.popleft()
            case _:
                raise Exception("Unexpected button press event received")

        await self.mount_next_question()

    async def clear_widgets(self) -> None:
        for child in self.walk_children():
            await child.remove()

        self.set_focus(None)

    async def mount_next_question(self) -> None:
        await self.clear_widgets()
        try:
            await self.mount(TrainingQuestion(self.questions[0]))
        except IndexError:
            pass
        await self.mount(Button("Skip", id="btn-action"))

    async def on_key(self, event: events.Key):
        if event.key == "escape":
            await self.clear_widgets()


class JoinOrHostScreen(Screen):
    def __init__(self, game_type: str):
        self.game_type = game_type
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Button("Join", id="btn-join")
        yield Button("Host", id="btn-host")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-host":
            self.app.push_screen(HostScreen(self.game_type))
        elif event.button.id == "btn-join":
            self.app.push_screen(JoinScreen(self.game_type))


class HostScreen(Screen):
    def __init__(self, game_type: str):
        self.game_type = game_type
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Lobby Name", id="lobby-name")
        yield Button("Create")

    def on_button_pressed(self, event: Button.Pressed):
        event.prevent_default()
        lobby_name = self.query_one("#lobby-name").value

        # TODO: Error handling
        data = self.app.client.create_lobby(lobby_name, ranked=self.game_type == "ranked")

        self.app.install_screen(self)
        self.app.switch_screen(GameScreen(lobby_name, data["token"]))
        self.app.uninstall_screen(self)

    def on_screen_resume(self):
        self.query_one(Input).value = ""


class JoinScreen(Screen):
    def __init__(self, game_type: str):
        self.game_type = game_type
        super().__init__()

    def compose(self) -> ComposeResult:
        lobbies = self.app.client.get_lobbies(ranked=self.game_type == "ranked")

        for lobby in lobbies:
            yield Button(lobby["name"])

    def on_button_pressed(self, event: Button.Pressed):
        lobby_name = event.button.label

        data = self.app.client.join_lobby(lobby_name)

        self.app.install_screen(self)
        self.app.switch_screen(GameScreen(lobby_name, data["token"]))
        self.app.uninstall_screen(self)


class GameScreen(Screen):
    def __init__(self, lobby: str, token: str):
        self.lobby = lobby
        self.token = token
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

        self.questions: Optional[list[dict]] = None
        self.current_question: int = 0
        self.first_question_received: bool = False
        self.fifty_fifty_chance: bool = True

        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static("Loading In...")

    async def on_mount(self):
        self.ws = await self.app.client.ws_join_lobby(self.lobby, self.token)
        asyncio.create_task(self.receive_ws())

    async def receive_ws(self) -> None:
        with suppress(websockets.ConnectionClosedOK):
            while True:
                event = await self.ws.recv()
                await self.handle_ws_event(json.loads(event))

    async def handle_ws_event(self, event) -> None:
        if event["type"] == "game.prepare":
            await self.ws.send(json.dumps({"type": "game.ready"}))

        elif event["type"] == "game.start":
            opponent_name = event["opponent"]
            duration = event["duration"]

            await self.clear_widgets()
            await self.mount(GameHeader(self.app.username, opponent_name, duration))
            await self.mount(Container(id="container-question"))

        elif event["type"] == "question.data":
            self.questions = event["questions"]
            self.current_question = 0

        elif event["type"] == "question.next":
            if self.first_question_received:
                await asyncio.sleep(1)
            else:
                self.first_question_received = True

            await self.next_question()

        elif event["type"] == "question.result":
            question_container = self.query_one("#container-question", Container)
            question_container.query_one(Question).highlight_answers(event["correct_answer"], event["correctly"])
            self.query_one(GameHeader).decrease_player_hp(int(event["damage"]))

        elif event["type"] == "fifty.response":
            await self.query_one(Question).post_message(
                FiftyFiftyTriggered(self, incorrect_answers=event["incorrect_answers"])
            )

        elif event["type"] == "game.end":
            await asyncio.sleep(1)
            await self.game_end(event["status"])

        elif event["type"] == "opponent.answered":
            self.query_one(GameHeader).decrease_opponent_hp(int(event["damage"]))

    async def next_question(self) -> None:
        question_container = self.query_one("#container-question", Container)
        for child in question_container.walk_children():
            await child.remove()
        self.set_focus(None)

        await question_container.mount(Question(self.questions[self.current_question]))

        if self.fifty_fifty_chance:
            await question_container.mount(Button("50/50", id="btn-5050"))

        self.current_question += 1

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
            case _:
                raise Exception("Unexpected button event received")

    async def on_question_answered(self, event: QuestionAnswered):
        if self.fifty_fifty_chance:
            question_container = self.query_one("#container-question", Container)
            question_container.query_one("#btn-5050", Button).disabled = True

        await self.ws.send(json.dumps({"type": "question.answered", "answer": event.answer}))

    async def game_end(self, status: str) -> None:
        await self.clear_widgets()

        await self.mount(GameStatus(status))
        await self.ws.close()

    async def on_key(self, event: events.Key):
        if event.key == "escape":
            if self.ws:
                await self.ws.close()
            await self.clear_widgets()

    async def clear_widgets(self) -> None:
        for child in self.walk_children():
            await child.remove()

        self.set_focus(None)


class UserRankingScreen(Screen):
    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("user", "rank")

        rankings = ((ranking["username"], str(ranking["rank"])) for ranking in self.app.client.get_rankings())
        table.add_rows(rankings)

        table.focus()


class GameHistoryScreen(Screen):
    def compose(self) -> ComposeResult:
        games = self.app.client.get_user_games()
        if games:
            yield GameHistoryTable(games)
        yield Static("You have not played any games yet!")

    def on_mount(self):
        try:
            self.query_one(GameHistoryTable).focus()
        except NoMatches:
            pass
