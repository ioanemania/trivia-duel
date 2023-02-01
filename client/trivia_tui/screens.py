from typing import Optional

import json

from contextlib import suppress

import asyncio
from requests.auth import AuthBase

import websockets

from textual import events
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Input, Static, DataTable

from .widgets import Question, GameStatus
from .messages import QuestionAnswered


class TokenAuth(AuthBase):
    def __init__(self, token: str, auth_scheme="Bearer"):
        self.token = token
        self.auth_scheme = auth_scheme

    def __call__(self, request):
        request.headers["Authorization"] = f"{self.auth_scheme} {self.token}"
        return request


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
            await self.app.push_screen(MainMenuScreen())

    def query_credentials(self) -> tuple[str, str]:
        username = self.query_one("#username").value
        password = self.query_one("#password").value
        return username, password


class MainMenuScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Button("Play", id="btn-play")
        yield Button("Leaderboard", id="btn-leaderboard")
        yield Button("History", disabled=True)

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-play":
            await self.app.push_screen(PlayMenuScreen())
        elif event.button.id == "btn-leaderboard":
            await self.app.push_screen(UserRankingScreen())


class PlayMenuScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Button("Ranked", id="btn-ranked")
        yield Button("Normal", id="btn-normal")
        yield Button("Training", id="btn-training", disabled=True)

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-ranked":
            await self.app.push_screen(JoinOrHostScreen("ranked"))
        elif event.button.id == "btn-normal":
            await self.app.push_screen(JoinOrHostScreen("normal"))
        else:
            pass  # training


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

        self.questions: dict | None = None
        self.current_question: int = 0

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
        if event["type"] == "game.start":
            self.questions = event["questions"]
            self.current_question = 1
            await self.next_question()
        elif event["type"] == "question.next":
            await self.next_question()
        elif event["type"] == "game.end":
            await self.game_end(event["status"])

    async def next_question(self) -> None:
        self.current_question += 1

        await self.clear_widgets()

        await self.mount(Question(**self.questions[self.current_question]))

    async def on_question_answered(self, event: QuestionAnswered):
        await self.ws.send(
            json.dumps(
                {
                    "type": "question.answered",
                    "correctly": event.correctly,
                    "difficulty": event.difficulty,
                }
            )
        )

    async def game_end(self, status: str) -> None:
        await self.clear_widgets()

        await self.mount(GameStatus(status))
        await self.ws.close()

    async def on_key(self, event: events.Key):
        if event.key == "escape" and len(self.app.screen_stack) > 2:
            if self.ws:
                await self.ws.close()

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
