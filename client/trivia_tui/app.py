from textual import events
from textual.app import App

from .screens import LoginOrRegisterScreen
from .clients import TriviaClient

TRIVIA_SERVER_URL = "localhost:8000/"


class TriviaApp(App):
    def __init__(self, *args, **kwargs):
        self.client = TriviaClient(TRIVIA_SERVER_URL)
        self.access_token: str | None = None

        super().__init__(*args, **kwargs)

    def on_mount(self) -> None:
        self.push_screen(LoginOrRegisterScreen())

    def on_key(self, event: events.Key):
        if event.key == "escape" and len(self.screen_stack) > 3:
            self.pop_screen()
